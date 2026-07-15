import json
import pandas as pd
import pytest
from provider_app import identity, jhe_data
from provider_app.launch_context import LaunchContext


def _context():
    return LaunchContext(
        access_token="ehr-access-token",
        id_token="ehr-id-token",
        fhir_base="https://ehr.example.org/fhir",
        fhir_patient_id="pat-1",
        patient_mrn="MRN-1",
    )


class _EhrResp:
    """Fake EHR FHIR Patient response (family Nguyen / DOB 1984-07-11)."""

    def __init__(self, family="Nguyen", birth_date="1984-07-11"):
        self._family = family
        self._birth_date = birth_date

    def raise_for_status(self):
        pass

    def json(self):
        body = {"id": "pat-1"}
        if self._family is not None:
            body["name"] = [{"family": self._family, "given": ["May"]}]
        if self._birth_date is not None:
            body["birthDate"] = self._birth_date
        return body


def _ehr_get(family="Nguyen", birth_date="1984-07-11"):
    return lambda url, headers=None: _EhrResp(family=family, birth_date=birth_date)


class FakeClient:
    """JHE client whose record matches the default EHR identity (Nguyen / 1984-07-11)."""

    def __init__(self, name_family="Nguyen", birth_date="1984-07-11"):
        self.calls = []
        self._name_family = name_family
        self._birth_date = birth_date

    def list_patients(self, organization_id=None, study_id=None):
        yield {"id": 7, "identifier": "MRN-1"}

    def get_patient(self, patient_id):
        return {"id": patient_id, "nameFamily": self._name_family, "birthDate": self._birth_date}

    def list_observations_df(self, patient_id=None, code=None, limit=2000):
        self.calls.append((patient_id, code, limit))
        return pd.DataFrame(
            {
                "effective_time_frame_date_time": pd.to_datetime(
                    ["2026-06-01T00:00:00Z", "2026-06-05T00:00:00Z"], utc=True
                ),
                "heart_rate_value": [60, 72],
            }
        )


def test_fetch_returns_dict_of_dataframes(monkeypatch):
    monkeypatch.setattr(identity.requests, "get", _ehr_get())
    client = FakeClient()
    result = jhe_data.fetch(_context(), types=["heart_rate"], client=client)
    assert set(result.keys()) == {"heart_rate"}
    assert isinstance(result["heart_rate"], pd.DataFrame)
    assert len(result["heart_rate"]) == 2
    # patient resolved to id 7, queried with the heart-rate code
    assert client.calls[0][0] == 7


def test_fetch_filters_by_date_range(monkeypatch):
    monkeypatch.setattr(identity.requests, "get", _ehr_get())
    client = FakeClient()
    result = jhe_data.fetch(
        _context(), types=["heart_rate"], client=client,
        start="2026-06-03", end="2026-06-10",
    )
    assert len(result["heart_rate"]) == 1  # only the 2026-06-05 row


def test_fetch_end_date_includes_intraday_observations(monkeypatch):
    monkeypatch.setattr(identity.requests, "get", _ehr_get())

    # `end` is an inclusive calendar date: a non-midnight reading on the end day is kept.
    class IntradayClient(FakeClient):
        def list_observations_df(self, patient_id=None, code=None, limit=2000):
            return pd.DataFrame({
                "effective_time_frame_date_time": pd.to_datetime(
                    ["2026-06-10T10:30:00Z", "2026-06-11T00:00:00Z"], utc=True
                ),
                "heart_rate_value": [80, 90],
            })

    result = jhe_data.fetch(
        _context(), types=["heart_rate"], client=IntradayClient(),
        start="2026-06-01", end="2026-06-10",
    )
    # the 2026-06-10 10:30 reading is kept; the 2026-06-11 reading is excluded
    assert len(result["heart_rate"]) == 1


def test_fetch_filters_interval_timestamped_data_by_date_range(monkeypatch):
    # Interval-based measures (e.g. wearable heart rate) carry the interval start
    # column instead of the point column; start/end must filter those too
    # (previously a silent no-op that returned the unfiltered frame).
    monkeypatch.setattr(identity.requests, "get", _ehr_get())

    class IntervalClient(FakeClient):
        def list_observations_df(self, patient_id=None, code=None, limit=2000):
            self.calls.append((patient_id, code, limit))
            return pd.DataFrame({
                "effective_time_frame_time_interval_start_date_time": pd.to_datetime(
                    ["2026-06-01T00:00:00Z", "2026-06-05T00:00:00Z"], utc=True
                ),
                "heart_rate_value": [60, 72],
            })

    result = jhe_data.fetch(
        _context(), types=["heart_rate"], client=IntervalClient(),
        start="2026-06-03", end="2026-06-10",
    )
    assert len(result["heart_rate"]) == 1  # only the 2026-06-05 row


def test_fetch_raises_on_identity_mismatch(monkeypatch):
    # JHE record is a different person (family Smith) than the launched EHR patient (Nguyen).
    monkeypatch.setattr(identity.requests, "get", _ehr_get(family="Nguyen"))
    client = FakeClient(name_family="Smith")
    with pytest.raises(identity.IdentityMismatch):
        jhe_data.fetch(_context(), types=["heart_rate"], client=client)
    # no observation query ran once the guard failed
    assert client.calls == []


def test_fetch_raises_when_ehr_identity_unreadable(monkeypatch):
    # EHR Patient fetch fails -> fail closed (IdentityUnverified), never read data.
    import requests as _requests

    def _boom(url, headers=None):
        raise _requests.ConnectionError("EHR unreachable")

    monkeypatch.setattr(identity.requests, "get", _boom)
    client = FakeClient()
    with pytest.raises(identity.IdentityUnverified):
        jhe_data.fetch(_context(), types=["heart_rate"], client=client)
    assert client.calls == []


def test_data_type_codes_env_override(monkeypatch):
    monkeypatch.setenv("JHE_DATA_TYPE_CODES", json.dumps({"steps": "omh:step-count:9.9"}))
    assert jhe_data.code_for("steps") == "omh:step-count:9.9"


def test_unknown_data_type_raises():
    with pytest.raises(jhe_data.UnknownDataType):
        jhe_data.code_for("blood_pressure_made_up")


def test_fetch_uses_one_unfiltered_high_limit_call(monkeypatch):
    # Robustness: a single fetch with NO server-side code= filter (which silently
    # drops IEEE-namespaced codes) and a limit well above the API's 2000-row default.
    monkeypatch.setattr(identity.requests, "get", _ehr_get())
    client = FakeClient()
    jhe_data.fetch(_context(), types=["heart_rate"], client=client)
    assert len(client.calls) == 1
    _patient_id, code, limit = client.calls[0]
    assert code is None
    assert limit >= 100_000


def test_fetch_returns_ieee_coded_rows_server_filtering_would_drop(monkeypatch):
    # `sleep` maps to an IEEE-namespaced code; server-side code= filtering returns
    # nothing for it, so this proves the client-side split surfaces the row.
    monkeypatch.setattr(identity.requests, "get", _ehr_get())
    sleep_code = jhe_data._code_string(jhe_data.code_for("sleep"))

    class MixedClient(FakeClient):
        def list_observations_df(self, patient_id=None, code=None, limit=2000):
            self.calls.append((patient_id, code, limit))
            return pd.DataFrame(
                {
                    "code_coding_0_code": [sleep_code, "omh:heart-rate:2.0"],
                    "effective_time_frame_date_time": pd.to_datetime(
                        ["2026-06-01T00:00:00Z", "2026-06-02T00:00:00Z"], utc=True
                    ),
                }
            )

    client = MixedClient()
    result = jhe_data.fetch(_context(), types=["sleep"], client=client)
    assert len(result["sleep"]) == 1            # the IEEE-coded sleep row, split client-side
    assert client.calls[0][1] is None           # fetched unfiltered
