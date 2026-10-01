"""Resolve an EHR MRN to a JupyterHealth Exchange patient id.

Default strategy: JHE stores the MRN as the patient's external identifier, so we
look the patient up by external_id. Override via set_resolver() for institutions
whose mapping differs.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

_override: Callable[[str, Any], int] | None = None


class PatientNotInJHE(Exception):
    """Raised when no JHE patient matches the given MRN."""


def set_resolver(resolver: Callable[[str, Any], int] | None) -> None:
    """Install a custom MRN -> jhe_patient_id resolver, or None to reset to default."""
    global _override
    _override = resolver


def _has_external_id(patient: Any, mrn: str) -> bool:
    """Whether a JHE patient record carries the given external id (MRN).

    JHE represents the external identifier two ways depending on version: a
    singular ``identifier`` string, or an ``identifiers`` array of
    ``{"system", "value"}``. Match either form (on value; the EHR and JHE systems
    need not agree).
    """
    if patient.get("identifier") == mrn:
        return True
    return any(ident.get("value") == mrn for ident in patient.get("identifiers") or [])


def _default_resolver(mrn: str, client: Any) -> int:
    for patient in client.list_patients():
        if _has_external_id(patient, mrn):
            return patient["id"]
    raise PatientNotInJHE(f"No JupyterHealth patient found for MRN {mrn!r}.")


def resolve_patient(mrn: str, client: Any) -> int:
    """Return the JHE patient id for the given MRN."""
    resolver = _override if _override is not None else _default_resolver
    return resolver(mrn, client)
