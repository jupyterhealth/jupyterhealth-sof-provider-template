"""Fetch a patient's device data from the JupyterHealth Exchange.

Returns one tidy pandas DataFrame per requested data type (the OMH types are
heterogeneous, so we keep them separate rather than forcing one schema).
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

import pandas as pd
from jupyterhealth_client import Code, JupyterHealthClient

from . import identity, patient_resolver

# Friendly data-type name -> JHE code. Code enum members where available;
# string OMH/IEEE codes otherwise. These must match the code the patient's data
# was actually ingested under — confirm against your ingestion path (Garmin shim /
# Validic / synthea) and override via JHE_DATA_TYPE_CODES.
_DEFAULT_DATA_TYPE_CODES: dict[str, object] = {
    "heart_rate": Code.HEART_RATE,
    "sleep": Code.SLEEP_STAGE_SUMMARY,
    "steps": "omh:step-count:3.0",
}

# OMH effective time is a point (…date_time) or an interval (…start_date_time)
# depending on the measure; date filtering uses whichever the frame carries.
_TIME_COLUMNS = (
    "effective_time_frame_date_time",
    "effective_time_frame_time_interval_start_date_time",
)

# High enough to never hit the JHE API's default 2000-row page cap on a single
# unfiltered fetch (see fetch() for why we fetch unfiltered).
_OBSERVATION_FETCH_LIMIT = 100_000

# The flattened observations frame names the code column one of these.
_CODE_COLUMNS = ("code_coding_0_code", "code")


class UnknownDataType(Exception):
    """Raised when a requested data type has no configured JHE code."""


def _configured_codes() -> dict[str, object]:
    codes = dict(_DEFAULT_DATA_TYPE_CODES)
    override = os.environ.get("JHE_DATA_TYPE_CODES")
    if override:
        codes.update(json.loads(override))
    return codes


def code_for(data_type: str) -> object:
    codes = _configured_codes()
    if data_type not in codes:
        raise UnknownDataType(
            f"No JHE code configured for data type {data_type!r}. "
            f"Add it via JHE_DATA_TYPE_CODES."
        )
    return codes[data_type]


def _code_string(code: object) -> str:
    """Normalize a configured code (a `Code` enum member or a raw string) to its
    OMH/IEEE code string, e.g. Code.HEART_RATE -> 'omh:heart-rate:2.0'."""
    return str(getattr(code, "value", code))


def _filter_dates(df: pd.DataFrame, start: Optional[str], end: Optional[str]) -> pd.DataFrame:
    time_column = next((c for c in _TIME_COLUMNS if c in df.columns), None)
    if df.empty or time_column is None:
        return df
    if start is not None:
        df = df[df[time_column] >= pd.Timestamp(start, tz="UTC")]
    if end is not None:
        # `end` is an inclusive calendar date: keep all observations up to the
        # end of that day (otherwise intraday readings on `end` would be dropped).
        end_exclusive = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
        df = df[df[time_column] < end_exclusive]
    return df


def fetch(
    ctx,
    types: list[str],
    client: Optional[Any] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> dict[str, pd.DataFrame]:
    """Resolve the launched patient in JHE and return {data_type: tidy DataFrame}.

    `ctx` is the LaunchContext: its MRN is resolved to a JHE patient, and the
    resolved record is identity-checked against the EHR Patient before any data is
    returned (identity.assert_same_patient raises IdentityMismatch / IdentityUnverified
    if it can't be confirmed they are the same person — failing closed). Taking the
    full context here, rather than a bare MRN, makes that guard unavoidable.

    `client` defaults to a JupyterHealthClient built from $JHE_URL and the launch
    token. `start`/`end` are inclusive ISO dates applied client-side.
    """
    if client is None:
        client = JupyterHealthClient()
    patient_id = patient_resolver.resolve_patient(ctx.patient_mrn, client=client)
    jhe_patient = client.get_patient(patient_id)
    identity.assert_same_patient(ctx, jhe_patient)  # raises IdentityMismatch / IdentityUnverified

    # Fetch the patient's observations ONCE, unfiltered, then split by code in pandas.
    # Why not let the server filter per type with `code=`:
    #   1. The JHE API silently returns NOTHING for IEEE-namespaced codes (e.g.
    #      ieee:physical-activity:1.0, ieee:sleep-stage-summary:1.0) — activity/sleep
    #      data disappears with no error.
    #   2. Each per-type call also risks the API's default 2000-row truncation.
    # A single high-limit unfiltered call + client-side split is robust to both. The
    # resulting per-type frame is identical to a (working) server-filtered fetch.
    all_obs = client.list_observations_df(patient_id=patient_id, limit=_OBSERVATION_FETCH_LIMIT)
    code_col = next((c for c in _CODE_COLUMNS if c in all_obs.columns), None)

    out: dict[str, pd.DataFrame] = {}
    for data_type in types:
        wanted = _code_string(code_for(data_type))
        if all_obs.empty or code_col is None:
            df = all_obs.copy()  # nothing to split on; pass through (e.g. empty result)
        else:
            df = all_obs[all_obs[code_col].astype(str) == wanted].dropna(axis=1, how="all").copy()
        out[data_type] = _filter_dates(df, start, end)
    return out
