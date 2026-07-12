"""End-to-end smoke test: run dashboard.ipynb's code against fakes.

Proves launch_context -> jhe_auth -> jhe_data.fetch (identity guard included) ->
notebook viz wire together without a real EHR or JHE. Executes the notebook's code
cells in-process with fakes injected (a real kernel would not see in-process
monkeypatches). Run from the project root: `pytest tests/test_smoke.py`.

Asserts the DEFAULT scaffold's contract (a `data` dict containing `heart_rate`,
plus the fail-closed identity guard). If you replace dashboard.ipynb — e.g.
`cp examples/cgm-dashboard.ipynb dashboard.ipynb` — or change the scaffold cell,
adapt these assertions or skip this test.
"""
import json
from pathlib import Path

import nbformat
import pandas as pd
import plotly.io as pio

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class FakeJheClient:
    """Stands in for JupyterHealthClient. Default identity matches the fake EHR
    patient (Nguyen / 1984-07-11); pass a different name_family to simulate a
    stale/wrong MRN mapping."""

    def __init__(self, url=None, token=None, name_family="Nguyen"):
        self._name_family = name_family
        self.observation_calls = []

    def get_user(self):
        return {"firstName": "Test", "lastName": "Practitioner", "email": "t@example.org"}

    def list_patients(self, organization_id=None, study_id=None):
        yield {"id": 7, "identifier": "MRN-1"}

    def get_patient(self, patient_id):
        return {"id": patient_id, "nameFamily": self._name_family, "birthDate": "1984-07-11"}

    def list_observations_df(self, patient_id=None, code=None, limit=2000):
        self.observation_calls.append((patient_id, code, limit))
        return pd.DataFrame({
            "code_coding_0_code": ["omh:heart-rate:2.0", "omh:heart-rate:2.0"],
            "effective_time_frame_date_time": pd.to_datetime(
                ["2026-06-01T00:00:00Z", "2026-06-01T01:00:00Z"], utc=True
            ),
            "heart_rate_value": [65, 72],
        })


def _run_dashboard(tmp_path, monkeypatch, jhe_client):
    """Execute every code cell of dashboard.ipynb with fakes; return the namespace."""
    import sys
    sys.path.insert(0, str(PROJECT_ROOT))
    from provider_app import jhe_auth, launch_context

    # Fake SMART token file + env
    token_file = tmp_path / "smart_token.json"
    token_file.write_text(json.dumps({
        "token": {"access_token": "TEST", "id_token": "TEST-ID-TOKEN", "patient": "P1", "scope": "patient/*.read openid fhirUser"},
        "fhir_url": "https://fhir.test",
        "smart_config": {},
    }))
    monkeypatch.setenv("SMART_TOKEN_FILE", str(token_file))
    monkeypatch.setenv("MRN_IDENTIFIER_SYSTEM", "urn:mrn")
    monkeypatch.setenv("JHE_URL", "https://jhe.test")
    monkeypatch.setenv("MPLBACKEND", "Agg")  # keep matplotlib headless

    # Mock the JHE token exchange so jhe_auth.client_for_launch runs its real code
    # path, and swap in the fake client where it constructs JupyterHealthClient.
    monkeypatch.setattr(jhe_auth, "exchange_token", lambda ctx, *a, **k: "TEST-JHE-TOKEN")
    monkeypatch.setattr(jhe_auth, "JupyterHealthClient", lambda url=None, token=None: jhe_client)

    # Fake the EHR FHIR Patient fetch. Patching requests.get on the shared module
    # covers both readers: launch_context.current() (MRN extraction) and
    # identity.ehr_identity() (the same-person guard inside jhe_data.fetch).
    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "id": "P1",
                "identifier": [{"system": "urn:mrn", "value": "MRN-1"}],
                "name": [{"family": "Nguyen", "given": ["May"]}],
                "birthDate": "1984-07-11",
                "gender": "female",
                "telecom": [],
            }

    monkeypatch.setattr(launch_context.requests, "get", lambda url, headers=None, **kw: _Resp())

    # Keep plotly headless (no browser). Empty string means "no renderer".
    pio.renderers.default = ""

    nb = nbformat.read(str(PROJECT_ROOT / "dashboard.ipynb"), as_version=4)
    namespace: dict = {}
    for cell in nb.cells:
        if cell.cell_type == "code":
            exec(compile(cell.source, "<dashboard-cell>", "exec"), namespace)
    return namespace


def test_notebook_code_executes(tmp_path, monkeypatch):
    client = FakeJheClient()
    ns = _run_dashboard(tmp_path, monkeypatch, client)

    # the scaffolded cell populated `data` with the fetched frames via the REAL
    # jhe_data.fetch (identity guard passed against the matching fake EHR patient)
    assert ns["access_note"] is None
    assert "data" in ns
    assert "heart_rate" in ns["data"]
    assert not ns["data"]["heart_rate"].empty


def test_notebook_fails_closed_on_identity_mismatch(tmp_path, monkeypatch):
    # JHE record is a different person than the launched EHR patient: the notebook
    # must show the access notice and never fetch observations.
    client = FakeJheClient(name_family="Smith")
    ns = _run_dashboard(tmp_path, monkeypatch, client)

    assert ns["access_note"] is not None
    assert "identity" in ns["access_note"].lower()
    assert ns["data"] == {}
    assert client.observation_calls == []
