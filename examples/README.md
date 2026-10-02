# Example dashboards

Drop-in notebooks for this provider app. Each is launch-scoped: it reads the
SMART-launched patient via `provider_app.launch_context`, resolves the MRN to a JHE
patient, fetches that patient's data, and renders under Voilà.

> **These are optional starting points — not a step in setting up a project.** The normal
> workflow is to edit the `dashboard.ipynb` at the repo root (the cell marked
> `ADD YOUR ANALYTICS + VISUALIZATION`) with your own analytics. Copy one of these examples
> over `dashboard.ipynb` *only* if it's a better starting point than writing your own:
> `cp examples/cgm-dashboard.ipynb dashboard.ipynb`.

## `cgm-dashboard.ipynb` — Continuous Glucose Monitoring (AGP report + multi-signal showcase)

A single-patient CGM report: glycemic metrics (Mean, GMI, CV, Time-in-Range, GRI),
an Ambulatory Glucose Profile (AGP) percentile chart, and a Time-in-Range bar. The
analytics are adapted from the JupyterHealth
[CGM tutorial](https://jupyterhealth.github.io/software-documentation/tutorial/tutorial-cgm/),
rewired to run off the launch context instead of hardcoded ids.

After the report, a **"what's possible" showcase** (separated by a divider) demonstrates a
richer, interactive view built entirely in the notebook with Plotly + ipywidgets: the same
patient's glucose overlaid with sleep, activity, and overnight vitals (HR/RR/SpO₂) in a
tabbed dashboard (Master Overlay, an Anatomy-of-a-Day drill-down with a live normal-range
slider, and Overnight small-multiples). It pulls those extra signals live from JHE, auto-
scopes to the dense multi-signal window, and degrades gracefully — a glucose-only patient
still gets the report, with the showcase quietly noting the absent signals.

### Use it in your project

1. Copy it over the dashboard at the repo root (Voilà renders `default_url`,
   `dashboard.ipynb`; in Docker only `dashboard.ipynb` is under `root_dir`
   (`/app/notebooks`), while locally any notebook under the project directory can be
   rendered):
   ```
   cp examples/cgm-dashboard.ipynb dashboard.ipynb
   ```
2. It needs `matplotlib`, `ipywidgets`, and `anywidget` — all already in this app's
   `pyproject.toml` (the latter two back the interactive showcase's Plotly `FigureWidget`).
   No `cgmquantify`.
3. Iterate on visuals without a live launch using the **dev fallback** in the scaffold
   cell (comment the launch lines, hardcode `patient_id = 40006`; needs `$JHE_URL` and a
   JHE client/token you supply in the notebook for local-only iteration).

> Once you copy this over `dashboard.ipynb`, `tests/test_smoke.py` will fail — it asserts
> the default scaffold's `data`/`heart_rate` contract, which this notebook doesn't use.
> That's expected; adapt or skip that test for your customized dashboard.

### Auth model

There is **no separate JHE login**: the provider logs into the **EHR** (Medplum) during the
SMART launch, and `provider_app/jhe_auth.py` exchanges the EHR id_token for a JHE token
(RFC 8693) on every launch, authenticating as the app's JHE confidential client
(`JHE_CLIENT_ID` / `JHE_CLIENT_SECRET`). JHE must be configured to trust the EHR issuer
(the `auth.sof.trusted_issuers` / `auth.sof.trusted_audience` settings) — see
`docs/QUICKSTART.md`.

## Reproducible demo values — Medplum (EHR) + jhe.fly.dev (JHE)

Verified against the fly.dev iglu seed (study **30006 — Iglu CGM Test Data**).

### The demo patient (recreate in Medplum)

| Field | Value |
|---|---|
| Given name | May |
| Family name | Nguyen |
| Birth date | 1984-07-11 |
| **`Patient.identifier.value`** | **`1636-69-001`** (confirm in the JHE portal → Patients → 40006) |
| `Patient.identifier.system` | whatever you set as `MRN_IDENTIFIER_SYSTEM` (you control both sides) |
| JHE patient id | 40006 |
| Data | ~1,846 `blood-glucose` (MGDL), Jan 2023 → Mar 2024, + some sleep/HR/SpO2 |

The resolver matches on identifier **value** only, so the EHR and JHE identifier
*systems* need not agree — just make the **values equal**.

### `.env`

```
JHE_URL=https://jhe.fly.dev
MRN_IDENTIFIER_SYSTEM=<the system you stamped on the Medplum patient>
SMART_ALLOWED_ISSUERS=https://api.medplum.com/fhir/R4
# JHE checks the id_token iss (https://api.medplum.com/) against auth.sof.trusted_issuers;
# JHE_TRUSTED_ISS is still sent for older JHE but current JHE ignores it
JHE_TRUSTED_ISS=https://api.medplum.com/
```
The app mints its JHE token at launch via the id_token exchange, so there is no token to set.

### `.env` values that matter

```
JHE_URL=https://jhe.fly.dev
SMART_CLIENT_ID=<your Medplum SMART client_id>
# Launch iss (FHIR base) allowed to open the app; the server refuses to start without it
SMART_ALLOWED_ISSUERS=https://api.medplum.com/fhir/R4
# Optional: current JHE ignores this and checks the id_token iss against auth.sof.trusted_issuers
JHE_TRUSTED_ISS=https://api.medplum.com/
EHR_IFRAME_ORIGIN=https://app.medplum.com            # unused by Medplum (redirect launch); only iframe EHRs need it
MRN_IDENTIFIER_SYSTEM=<same system as the Medplum patient identifier>
```

Set these in your gitignored `.env` (copy from `.env.example`); the app mints its JHE
token at launch via the id_token exchange, so there's no token to add. The CGM notebook
fetches `blood_glucose` directly, and the FHIR base comes from the SMART launch token.

### Medplum app registration

- Launch URL:   `http://localhost:8888/smart-on-fhir/launch`
- Redirect URL: `http://localhost:8888/smart-on-fhir/callback`
- Scopes:       `openid fhirUser launch patient/*.read`
