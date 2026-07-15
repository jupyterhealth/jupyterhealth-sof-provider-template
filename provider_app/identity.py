"""Verify the launched EHR patient is the same person as the resolved JHE record.

The MRN join (patient_resolver) is the only link between the EHR and JHE; a wrong
or stale external identifier in JHE would silently surface another patient's data.
This guard re-reads the EHR Patient's demographics from the SMART launch and refuses
to proceed unless they match the JHE record. It fails CLOSED: if the EHR identity
cannot be read at all, we raise rather than display anything.

We compare family name + birth date only. Given names vary legitimately (nicknames,
e.g. May/Mary) and would cause false mismatches; family name + DOB is a robust,
low-false-positive check for "same person" in this single-MRN lookup context.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

import requests


class IdentityError(Exception):
    """Base class for identity-verification failures."""


class IdentityUnverified(IdentityError):
    """The EHR identity could not be read; we fail closed and refuse to display."""


class IdentityMismatch(IdentityError):
    """The JHE record does not match the launched EHR patient."""


def ehr_identity(ctx, http_get: Optional[Callable[..., Any]] = None) -> tuple[str, str]:
    """Return the launched EHR patient's (family_name_lower, birth_date).

    Reads ``{ctx.fhir_base}/Patient/{ctx.fhir_patient_id}`` with the SMART access
    token. Raises IdentityUnverified if the request fails, returns a non-200, or
    the FHIR resource is missing a family name or birthDate.

    `http_get` defaults to ``requests.get`` and can be injected for tests.
    """
    if http_get is None:
        http_get = requests.get

    url = f"{ctx.fhir_base.rstrip('/')}/Patient/{ctx.fhir_patient_id}"
    try:
        # Accept header required cross-vendor (Epic serves XML by default).
        resp = http_get(
            url,
            headers={
                "Authorization": f"Bearer {ctx.access_token}",
                "Accept": "application/fhir+json",
            },
        )
        resp.raise_for_status()
        patient = resp.json()
    except requests.RequestException as e:
        raise IdentityUnverified(
            f"Could not read EHR Patient/{ctx.fhir_patient_id} for identity check: {e}"
        ) from e

    family = None
    for name in patient.get("name") or []:
        if name.get("family"):
            family = name["family"]
            break
    birth_date = patient.get("birthDate")

    if not family or not birth_date:
        raise IdentityUnverified(
            f"EHR Patient/{ctx.fhir_patient_id} is missing family name or birthDate; "
            "cannot verify identity."
        )
    return family.lower(), birth_date


def assert_same_patient(ctx, jhe_patient: dict, http_get: Optional[Callable[..., Any]] = None) -> None:
    """Raise unless the JHE record is the same person as the launched EHR patient.

    Compares family name (case-insensitive) + birth date. Given name is NOT compared
    (legitimate nickname variants like May/Mary must pass). Raises:
      - IdentityUnverified (propagated from ehr_identity) if the EHR identity can't be read
      - IdentityMismatch if the family name or birth date differ
    """
    ehr_family, ehr_dob = ehr_identity(ctx, http_get=http_get)

    jhe_family = (jhe_patient.get("nameFamily") or "").lower()
    jhe_dob = jhe_patient.get("birthDate")

    if ehr_family != jhe_family or ehr_dob != jhe_dob:
        raise IdentityMismatch(
            "The JupyterHealth record does not match the launched patient; "
            "refusing to display data."
        )
