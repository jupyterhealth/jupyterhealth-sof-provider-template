# Quickstart

This walks you from a fresh clone of this template to seeing a patient's device data
rendered by a SMART on FHIR launch — end to end. Plan ~1–2 hours the first time.

There are two test paths for the SMART launch:
- **MedPlum** (recommended) — JupyterHealth's hosted demonstration Provider. No local
  EHR to run.
- **Fully local** — the self-contained
  [`jhe-smart-demo`](https://github.com/jupyterhealth/jhe-smart-demo) (HAPI FHIR + a
  mock EHR SMART App Launcher + JHE in docker compose). Use this if you want everything
  on your machine.

---

## 0. Prerequisites

- Python 3.11+ and Docker (with `docker compose`). For local (non-Docker) installs, use a
  virtualenv — `python3 -m venv .venv && source .venv/bin/activate` — since macOS/Homebrew
  Python rejects `pip install` outside one (PEP 668).
- Access to a **JupyterHealth Exchange (JHE) instance** — your own deployment, a shared
  `*.fly.dev` instance, or a local JHE (see
  [jupyterhealth-exchange](https://github.com/jupyterhealth/jupyterhealth-exchange)).
- In that JHE instance: a **Study**, at least one **Patient**, and some **Observations**
  for that patient (heart rate / sleep / steps).
- The patient's **MRN** must be stored on the JHE patient as its **external identifier**,
  and must match the MRN the EHR exposes on `Patient.identifier`. This is the join key.

> **How the app reaches JHE.** At launch the EHR gives the app an OIDC **id_token**.
> The app sends that token to JHE's `/o/token-exchange` (RFC 8693), authenticating as a
> **confidential OAuth client registered in JHE** (the token exchange runs server-side,
> so the secret never reaches the browser); JHE verifies the id_token offline against
> the EHR's JWKS, reads the `fhirUser` claim, maps it to a JHE Practitioner, and issues
> a JHE access token — no separate JHE login needed. For this to work JHE must trust
> the EHR issuer + this app's EHR `client_id` (the `auth.sof.*` settings), the app
> needs its JHE client credentials, and the launching Practitioner must exist in JHE
> keyed by the EHR's Practitioner id.

---

## 1. Get your JHE base URL and configure the token exchange

Note your JHE base URL — that's your `JHE_URL` (e.g. `https://jhe.fly.dev`). The app mints
its JHE token automatically from the SMART launch via the id_token exchange, so there is no
token to create or manage. Four things must be in place
(coordinate with whoever runs the JHE instance):

1. **Register the SMART app at the EHR** with `openid fhirUser` in the scopes so the EHR
   includes an id_token and a `fhirUser` claim in the launch response. See
   [ehr-registration.md](ehr-registration.md) for the full registration checklist.

2. **Get the app's JHE client credentials** — the token exchange requires the app to
   authenticate as a **confidential OAuth client registered in JHE**. `manage.py seed`
   creates one named "SoF EHR Launch" (dev-only credentials `sof-ehr-launch` /
   `sof-ehr-launch-dev-secret` — real deployments rotate them). These go in the app's
   `.env` as `JHE_CLIENT_ID` / `JHE_CLIENT_SECRET`; the secret stays server-side.

3. **Configure JHE to trust the EHR** — set these two `JheSetting` rows on the JHE
   instance (created by `manage.py seed`; edit via the JHE settings admin/API):
   - `auth.sof.trusted_issuers` (json array) — the EHR's OIDC issuer URL(s) (the `iss`
     in the id_token, typically the FHIR base URL, e.g. `https://fhir.ehr.example/r4`).
   - `auth.sof.trusted_audience` (string) — this app's `client_id` as registered at
     the EHR (the `aud` the EHR puts in the id_token).

4. **Seed the JHE Practitioner** — the launching clinician must exist in JHE with an
   `identifier` whose value equals the EHR's Practitioner id (the `fhirUser` claim in
   the id_token, e.g. `Practitioner/abc123` → id `abc123`).

---

## 2. Configure

Copy `.env.example` to `.env` (gitignored) and fill it in — `cp .env.example .env`, or
run `make init` for an interactive prompt. The app loads `.env` at runtime, so edits take
effect on the next run. Set:
- `JHE_URL` — from step 1 (e.g. `https://jhe.fly.dev`).
  **Must exactly match the JHE instance's `SITE_URL`** (same scheme and host, no trailing-slash
  difference) — the token-exchange `audience` check is an exact string comparison, so any
  mismatch causes every exchange to fail with HTTP 400.
- `JHE_CLIENT_ID` / `JHE_CLIENT_SECRET` — the app's JHE confidential client credentials
  from step 1 (dev default: `sof-ehr-launch` / `sof-ehr-launch-dev-secret`). The `.env`
  is gitignored and the exchange runs server-side, so the secret never leaves the backend.
- `SMART_CLIENT_ID` — the `client_id` from your EHR app registration (public client +
  PKCE; no secret); a placeholder works until you register, then paste the real value
- `SMART_SCOPES` — SMART scopes for the launch (the default is usually fine)
- `EHR_IFRAME_ORIGIN` — only for EHRs that iframe-embed the app (e.g. Epic); redirect
  launches like Medplum ignore it, so the default is fine
- `MRN_IDENTIFIER_SYSTEM` — the EHR `Patient.identifier` system that holds the MRN
  (see [ehr-registration.md](ehr-registration.md) §3 for how to find it; MedPlum has
  its own identifier system)
- `JHE_DATA_TYPE_CODES` (optional) — only if your data types differ from the defaults

---

## 3. Run the app

```
docker compose up --build
```
This starts the Jupyter server with the SMART launch extension and Voilà. It listens on
`http://localhost:8888`. It does nothing useful until an EHR launches it (next step) —
the launch is what supplies the patient context.

---

## 4. Simulate a SMART launch

### Path A — MedPlum (recommended)
Follow the upstream tutorial,
[*Launch a JupyterHealth dashboard via SMART on FHIR (MedPlum example)*](https://jupyterhealth.github.io/software-documentation/tutorial/medplum-provider-dashboard).
In short: register this app in MedPlum as a SMART app with:
- Launch URL: `http://localhost:8888/smart-on-fhir/launch`
- Redirect URL: `http://localhost:8888/smart-on-fhir/callback`

Then launch it from a MedPlum Patient's "Apps". MedPlum populates the launch context
(patient + token); the app reads the MRN and queries JHE.

### Path B — Fully local
Clone and run [`jhe-smart-demo`](https://github.com/jupyterhealth/jhe-smart-demo): its
docker compose brings up HAPI FHIR, a **mock EHR SMART App Launcher**, and JHE with a
seeded practitioner/patient. Point its launcher at this app's
`/smart-on-fhir/launch`. This is the closest local mirror of a real EHR launch.

If the launch succeeds you'll see the rendered notebook (your viz) where the patient's
data appears.

---

## 5. Develop your dashboard

The data plumbing is done — you write analytics/viz in **`dashboard.ipynb`**, in the cell
marked `ADD YOUR ANALYTICS + VISUALIZATION`.

Inner loop (faster than rebuilding the container each time):
```
python3 -m venv .venv && source .venv/bin/activate   # macOS/Homebrew: required (PEP 668)
pip install -e ".[test]"
jupyter lab            # open dashboard.ipynb, iterate on the viz cell
```
In Jupyter Lab the launch context isn't present, so `launch_context.current()` will
raise. For iterating on visuals, either run the smoke-test fakes pattern (see
`tests/test_smoke.py`) or temporarily hardcode a known MRN and call `jhe_data.fetch`
directly. When the viz looks right, `docker compose up --build` and re-launch to see it
in the SMART flow. Voilà renders exactly what the notebook produces.

Validate the wiring at any time without a server:
```
pytest tests/test_smoke.py
```

---

## 6. Register with your EHR and deploy

- [ehr-registration.md](ehr-registration.md) — register the app with your EHR, scopes,
  and starting your security review.
- [deployment.md](deployment.md) — deploy (Docker / fly.io), the **iframe/CSP gotcha**,
  and the POC single-provider concurrency limitation.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Blank frame in an **iframe-embedding** EHR (e.g. Epic) | CSP `frame-ancestors` blocks the embed (N/A to redirect launches like Medplum) | Set `EHR_IFRAME_ORIGIN` to the EHR origin; see deployment.md → "iframe/CSP gotcha" |
| `LaunchContextError: SMART_TOKEN_FILE is not set` | App opened without a SMART launch | Launch it from the EHR (step 4), not directly |
| `LaunchContextError: No identifier with system ... found` | `MRN_IDENTIFIER_SYSTEM` doesn't match the EHR's MRN system | Inspect the EHR `Patient.identifier` and set the correct system |
| `PatientNotInJHE: No JupyterHealth patient found for MRN ...` | JHE has no patient whose external id == that MRN | Add/align the patient's external identifier in JHE |
| `LaunchContextError: Failed to fetch Patient/...` | EHR token/scope issue or wrong FHIR base | Check the SMART scopes include `patient/*.read` and the EHR FHIR base |
| `TokenExchangeError` / "Client authentication failed" (401) | `JHE_CLIENT_ID` / `JHE_CLIENT_SECRET` missing from `.env` or wrong | Set them to the app's JHE confidential client credentials (step 1) |
| `TokenExchangeError` / "trusted issuer" | JHE's `auth.sof.trusted_issuers` setting doesn't include the EHR issuer, or `auth.sof.trusted_audience` doesn't match the app's EHR `client_id` | Add the EHR OIDC issuer to `auth.sof.trusted_issuers` and confirm `auth.sof.trusted_audience` equals this app's `client_id` at the EHR |
| `TokenExchangeError` / "Practitioner not found" | The EHR Practitioner id from `fhirUser` doesn't match any JHE Practitioner `identifier` | Seed the JHE Practitioner with an `identifier` equal to the EHR Practitioner id (step 1 above) |
| JHE calls return 401 | The exchanged JHE token was rejected (e.g. the launching Practitioner isn't on file in JHE, or trust isn't configured) | Confirm the token-exchange trust settings (step 1) and that the launching Practitioner exists in JHE |
| "No <type> data for this patient" | No observations of that type in JHE for the patient | Confirm data exists; check `JHE_DATA_TYPE_CODES` (esp. the provisional `steps` code) |
