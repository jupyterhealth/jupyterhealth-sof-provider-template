"""Read SMART launch context (token + patient MRN) for the current session.

All access to the SMART token goes through this module so the storage strategy
(currently the single global token file written by jupyter-smart-on-fhir) can be
swapped for per-session storage later without touching the notebook or data layer.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

import requests


class LaunchContextError(Exception):
    """Raised when the SMART launch context cannot be read or is incomplete."""


@dataclass
class LaunchContext:
    access_token: str
    id_token: str
    fhir_base: str
    fhir_patient_id: str
    patient_mrn: str


def _token_file_path() -> Path:
    path = os.environ.get("SMART_TOKEN_FILE")
    if not path:
        raise LaunchContextError(
            "SMART_TOKEN_FILE is not set; the SMART launch has not completed."
        )
    return Path(path)


def _read_token() -> dict[str, Any]:
    path = _token_file_path()
    try:
        return json.loads(path.read_text())
    except FileNotFoundError as e:
        raise LaunchContextError(f"Token file not found at {path}") from e
    except json.JSONDecodeError as e:
        raise LaunchContextError(f"Token file at {path} is not valid JSON") from e


def _extract_mrn(patient_resource: dict[str, Any], mrn_system: str) -> str:
    for identifier in patient_resource.get("identifier", []):
        if identifier.get("system") == mrn_system and identifier.get("value"):
            return identifier["value"]
    raise LaunchContextError(
        f"No identifier with system {mrn_system!r} found on patient "
        f"{patient_resource.get('id')!r}. Set MRN_IDENTIFIER_SYSTEM to the EHR's MRN system."
    )


def current(http_get: Optional[Callable[..., Any]] = None) -> LaunchContext:
    """Return the LaunchContext for the active SMART session.

    Raises LaunchContextError if the token is missing/incomplete or the MRN
    cannot be resolved from the EHR Patient resource.

    `http_get` is resolved at call time (defaulting to `requests.get`) so callers
    and tests can substitute it via injection or by patching `requests.get`.
    """
    if http_get is None:
        http_get = requests.get
    data = _read_token()
    token = data.get("token") or {}
    access_token = token.get("access_token")
    id_token = token.get("id_token")
    fhir_patient_id = token.get("patient")  # SMART token 'patient' field is the EHR patient resource ID
    fhir_base = data.get("fhir_url")
    if not access_token or not id_token or not fhir_patient_id or not fhir_base:
        raise LaunchContextError(
            "Token file is missing access_token, id_token, patient, or fhir_url. "
            "Ensure the SMART launch requests the 'openid fhirUser' scopes."
        )

    mrn_system = os.environ.get("MRN_IDENTIFIER_SYSTEM")
    if not mrn_system:
        raise LaunchContextError("MRN_IDENTIFIER_SYSTEM environment variable is not set.")

    url = f"{fhir_base.rstrip('/')}/Patient/{fhir_patient_id}"
    try:
        # Accept header is required cross-vendor: Epic serves XML unless
        # application/fhir+json is requested explicitly (MedPlum defaults to JSON).
        response = http_get(
            url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/fhir+json",
            },
        )
        response.raise_for_status()
        patient_resource = response.json()
    except requests.RequestException as e:
        raise LaunchContextError(
            f"Failed to fetch Patient/{fhir_patient_id} from the EHR FHIR server: {e}"
        ) from e

    return LaunchContext(
        access_token=access_token,
        id_token=id_token,
        fhir_base=fhir_base,
        fhir_patient_id=fhir_patient_id,
        patient_mrn=_extract_mrn(patient_resource, mrn_system),
    )
