# Registering this app with your EHR

This app is a **SMART on FHIR provider-launch** application. Register it under your
own EHR (Epic, Medplum, Cerner, etc.); The Commons Project is not involved in your
registration or security review.

## 1. Create the app in your EHR's developer / vendor portal
- App type: **Provider-facing (EHR launch)**
- Launch URL: `https://<your-host>/smart-on-fhir/launch`
- Redirect/OAuth callback URL: `https://<your-host>/smart-on-fhir/callback`
- Client type: **Public client (PKCE)**

> Where this lives depends on the EHR — e.g. the **Epic** App Orchard / vendor portal,
> or a **Medplum** ClientApplication / SMART App. The launch + redirect URLs and the
> PKCE public-client type are the same regardless.

## 2. Request these SMART scopes
```
openid fhirUser launch patient/*.read
```
`launch` is required for EHR launch; `patient/*.read` lets the app read the launched
patient. Add `fhirUser`/`openid` for identity. Set the scopes in `.env`
(`SMART_SCOPES`) to match what your EHR accepts:

- **Epic** does not honor wildcard scopes — request the explicit resource read. The
  grammar depends on the app registration's **SMART Scope Version**: SMART v1 →
  `patient/Patient.read`; SMART v2 → `patient/Patient.r`. The only EHR resource this
  app reads is `Patient`, so e.g. `SMART_SCOPES=openid fhirUser launch patient/Patient.r`
  for a v2 registration.
- **The id_token issuer is usually NOT the FHIR base.** JHE's `auth.sof.trusted_issuers`
  must contain the id_token's literal `iss` value. Per standard OIDC practice this is
  the EHR's dedicated OAuth server — e.g. Epic's sandbox issues
  `https://fhir.epic.com/interconnect-fhir-oauth/oauth2`, not the
  `…/api/FHIR/R4` base. (MedPlum is the outlier: its `iss` is the FHIR base URL, with a
  trailing slash.) When in doubt, decode a captured id_token and copy its `iss` verbatim.
- **Finding the MRN system on Epic:** inspect a test `Patient.identifier` — the MRN is
  the `EPI`-typed identifier (sandbox: `urn:oid:1.2.840.114350.1.13.0.1.7.5.737384.14`);
  each Epic install has its own OID.
- **Testing without an embedded EHR launch:** Epic's own hosted Hyperspace simulator
  covers this — on [fhir.epic.com](https://fhir.epic.com), open *Documentation →
  Launching* and use the "SMART on FHIR (OAuth 2.0)" launcher (pick app + test patient +
  your launch URL; Hyperspace sandbox login `FHIR` / `EpicFhir11!`). No vendor services
  subscription needed. New/edited registrations can take ~1h+ to sync to the sandbox —
  a generic "OAuth2 Error" or "Invalid OAuth 2.0 request" right after saving is usually
  just that lag.
- **MedPlum** accepts the wildcard default as-is.

## 3. Find your MRN identifier system
The app matches the EHR patient to JHE by MRN. In your EHR, inspect a test
`Patient.identifier` and copy the `system` value of the MRN identifier into
`MRN_IDENTIFIER_SYSTEM` (see deployment.md). On EHRs where you control the test data
(e.g. Medplum), set the identifier yourself so its value matches the JHE patient's
external id.

## 4. Start your institutional security review
Provide your security team: the deploy host, the SMART scopes above, and a note that
no PHI is persisted by the app (data is fetched per-session from JHE). Your security
review timeline is owned by your institution.
