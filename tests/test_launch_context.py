import json

import pytest

from provider_app import launch_context


def _write_token(tmp_path, patient="Patient123"):
    token_file = tmp_path / "smart_token.json"
    token_file.write_text(
        json.dumps(
            {
                "token": {
                    "access_token": "ABC",
                    "id_token": "ID-TOKEN",
                    "patient": patient,
                    "scope": "patient/*.read",
                },
                "fhir_url": "https://fhir.example.org",
                "smart_config": {},
            }
        )
    )
    return token_file


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
    token_file = _write_token(tmp_path)
    monkeypatch.setenv("SMART_TOKEN_FILE", str(token_file))
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


def test_missing_token_file_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("SMART_TOKEN_FILE", str(tmp_path / "nope.json"))
    with pytest.raises(launch_context.LaunchContextError):
        launch_context.current()


def test_missing_mrn_identifier_raises(tmp_path, monkeypatch):
    token_file = _write_token(tmp_path)
    monkeypatch.setenv("SMART_TOKEN_FILE", str(token_file))
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


def test_missing_token_file_env_var_raises(monkeypatch):
    monkeypatch.delenv("SMART_TOKEN_FILE", raising=False)
    with pytest.raises(launch_context.LaunchContextError):
        launch_context.current()


def test_ehr_http_error_wrapped(tmp_path, monkeypatch):
    import requests

    token_file = tmp_path / "smart_token.json"
    token_file.write_text(
        json.dumps(
            {
                "token": {
                    "access_token": "ABC",
                    "id_token": "ID-TOKEN",
                    "patient": "P1",
                    "scope": "patient/*.read",
                },
                "fhir_url": "https://fhir.example.org",
                "smart_config": {},
            }
        )
    )
    monkeypatch.setenv("SMART_TOKEN_FILE", str(token_file))
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
    token_file = tmp_path / "smart_token.json"
    token_file.write_text(
        json.dumps(
            {
                "token": {
                    "access_token": "ehr-access",
                    "id_token": "ehr-id-token",
                    "patient": "p1",
                },
                "fhir_url": "https://ehr.example.org/fhir",
            }
        )
    )
    monkeypatch.setenv("SMART_TOKEN_FILE", str(token_file))
    monkeypatch.setenv("MRN_IDENTIFIER_SYSTEM", "urn:mrn")

    ctx = launch_context.current(http_get=lambda url, headers=None: _FakePatient())
    assert ctx.id_token == "ehr-id-token"
