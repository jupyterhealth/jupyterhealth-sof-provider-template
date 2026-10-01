import pytest

from provider_app import patient_resolver


class FakeClient:
    def __init__(self, patients):
        self._patients = patients  # list of JHE patient records

    def list_patients(self, organization_id=None, study_id=None):
        yield from self._patients


def test_resolve_patient_matches_singular_identifier():
    # older JHE schema: a singular `identifier` string
    client = FakeClient([{"id": 42, "identifier": "MRN-1"}])
    assert patient_resolver.resolve_patient("MRN-1", client=client) == 42


def test_resolve_patient_matches_identifiers_array():
    # current JHE schema: an `identifiers` array of {system, value}
    client = FakeClient(
        [
            {"id": 7, "identifiers": [{"system": "other", "value": "X"}]},
            {
                "id": 42,
                "identifiers": [
                    {
                        "system": "https://openwearables.io/ns/patient-id",
                        "value": "abc",
                    },
                    {"system": "urn:oid:1.2.3.4", "value": "MRN-1"},
                ],
            },
        ]
    )
    assert patient_resolver.resolve_patient("MRN-1", client=client) == 42


def test_resolve_patient_not_found_raises_patientnotin_jhe():
    client = FakeClient([{"id": 1, "identifiers": [{"system": "s", "value": "other"}]}])
    with pytest.raises(patient_resolver.PatientNotInJHE):
        patient_resolver.resolve_patient("MRN-MISSING", client=client)


def test_resolver_override_hook():
    client = FakeClient({})
    patient_resolver.set_resolver(lambda mrn, c: 999)
    try:
        assert patient_resolver.resolve_patient("anything", client=client) == 999
    finally:
        patient_resolver.set_resolver(None)  # reset to default
