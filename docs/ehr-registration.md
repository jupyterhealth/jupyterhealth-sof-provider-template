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
- **Testing without an embedded EHR launch** (e.g. Epic's sandbox without vendor
  services): use a standalone launch by swapping `launch` for `launch/patient` and
  opening `/smart-on-fhir/launch?iss=<fhir-base>` directly — the EHR then prompts
  for login and patient selection itself.
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
