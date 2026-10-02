import base64
import json

import pytest

from provider_app import launch_context

SID = "t" * 32


def _signed_cookie(sid=SID, name="smart-session"):
    b = base64.b64encode(sid.encode()).decode()
    return f'{name}="2|1:0|10:1700000000|{len(name)}:{name}|{len(b)}:{b}|sig"'


def _write_token(tmp_path, patient="Patient123", token=None, fhir_url="https://fhir.example.org"):
    """Write a per-session token file; return the env the Voilà kernel would see."""
    (tmp_path / f"{SID}.json").write_text(
        json.dumps(
            {
                "token": token or {
                    "access_token": "ABC",
                    "id_token": "ID-TOKEN",
                    "patient": patient,
                    "scope": "patient/*.read",
                },
                "fhir_url": fhir_url,
                "smart_config": {},
                "expires_at": 4_000_000_000,
            }
        )
    )
    return {"SMART_TOKEN_DIR": str(tmp_path), "HTTP_COOKIE": f"_xsrf=1; {_signed_cookie()}"}


def _set_env(monkeypatch, env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)


def _patient_resource(mrn="MRN-999", system="urn:mrn"):
    return {
        "resourceType": "Patient",
        "id": "Patient123",
        "identifier": [
            {"system": "urn:other", "value": "X1"},
            {"system": system, "value": mrn},
        ],
    }


def test_current_reads_token_and_mrn(tmp_path, monkeypatch):
    _set_env(monkeypatch, _write_token(tmp_path))
    monkeypatch.setenv("MRN_IDENTIFIER_SYSTEM", "urn:mrn")

    captured = {}

    def fake_get(url, headers=None):
        captured["url"] = url
        captured["headers"] = headers

        class R:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return _patient_resource(mrn="MRN-999", system="urn:mrn")

        return R()

    ctx = launch_context.current(http_get=fake_get)
    assert ctx.access_token == "ABC"
    assert ctx.id_token == "ID-TOKEN"
    assert ctx.fhir_base == "https://fhir.example.org"
    assert ctx.fhir_patient_id == "Patient123"
    assert ctx.patient_mrn == "MRN-999"
    assert captured["url"] == "https://fhir.example.org/Patient/Patient123"
    assert captured["headers"]["Authorization"] == "Bearer ABC"


def test_unknown_session_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("SMART_TOKEN_DIR", str(tmp_path))
    monkeypatch.setenv("HTTP_COOKIE", _signed_cookie("z" * 32))
    with pytest.raises(launch_context.LaunchContextError, match="expired or not launched"):
        launch_context.current()


def test_missing_mrn_identifier_raises(tmp_path, monkeypatch):
    _set_env(monkeypatch, _write_token(tmp_path))
    monkeypatch.setenv("MRN_IDENTIFIER_SYSTEM", "urn:mrn")

    def fake_get(url, headers=None):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return _patient_resource(system="urn:DIFFERENT")

        return R()

    with pytest.raises(launch_context.LaunchContextError):
        launch_context.current(http_get=fake_get)


def test_missing_session_cookie_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("SMART_TOKEN_DIR", str(tmp_path))
    with pytest.raises(launch_context.LaunchContextError, match="session cookie"):
        launch_context.current()


def test_expired_session_file_raises(monkeypatch, tmp_path):
    env = _write_token(tmp_path)
    data = json.loads((tmp_path / f"{SID}.json").read_text())
    data["expires_at"] = 1
    (tmp_path / f"{SID}.json").write_text(json.dumps(data))
    _set_env(monkeypatch, env)
    with pytest.raises(launch_context.LaunchContextError, match="expired"):
        launch_context.current()


def test_ehr_http_error_wrapped(tmp_path, monkeypatch):
    import requests

    _set_env(monkeypatch, _write_token(tmp_path, patient="P1"))
    monkeypatch.setenv("MRN_IDENTIFIER_SYSTEM", "urn:mrn")

    def fake_get(url, headers=None):
        class R:
            def raise_for_status(self):
                raise requests.HTTPError("500 Server Error")

            def json(self):
                return {}

        return R()

    with pytest.raises(launch_context.LaunchContextError):
        launch_context.current(http_get=fake_get)


class _FakePatient:
    ok = True

    def json(self):
        return {"id": "p1", "identifier": [{"system": "urn:mrn", "value": "MRN-1"}]}

    def raise_for_status(self):
        pass


def test_launch_context_exposes_id_token(tmp_path, monkeypatch):
    _set_env(
        monkeypatch,
        _write_token(
            tmp_path,
            token={"access_token": "ehr-access", "id_token": "ehr-id-token", "patient": "p1"},
            fhir_url="https://ehr.example.org/fhir",
        ),
    )
    monkeypatch.setenv("MRN_IDENTIFIER_SYSTEM", "urn:mrn")

    ctx = launch_context.current(http_get=lambda url, headers=None: _FakePatient())
    assert ctx.id_token == "ehr-id-token"
