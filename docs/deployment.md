# Deploying this app

> **New here?** Start with [QUICKSTART.md](QUICKSTART.md) — it walks the full path from a
> fresh clone to data on screen (how to configure the id_token exchange, how to
> simulate a SMART launch). This file is the deployment-specific reference.

## Configure
Copy `.env.example` to `.env` (gitignored) and fill it in — `cp .env.example .env`, or
run `make init`. The app loads `.env` at runtime — edit it and the change takes effect on
the next run. Values:
- `JHE_URL` — your JupyterHealth Exchange base URL (e.g. `https://jhe.fly.dev`). The app
  mints its JHE bearer token at launch by exchanging the EHR id_token (RFC 8693); JHE must
  be configured to trust the EHR issuer — see [QUICKSTART.md](QUICKSTART.md) §1.
- `SMART_CLIENT_ID` — the SMART `client_id` from your EHR app registration (public
  client + PKCE; no secret).
- `SMART_SCOPES` — SMART scopes requested at launch (space-separated).
- `SMART_ALLOWED_ISSUERS` — **required.** Space-separated FHIR base URL(s) of the EHR(s) allowed
  to launch this app: the `iss` the EHR sends on the launch URL. The server refuses to start
  while this is empty. Never list a public sandbox on a production instance. This is **not**
  the same value as JHE's `auth.sof.trusted_issuers`, which holds the OIDC id_token issuer:

  | EHR | `SMART_ALLOWED_ISSUERS` (launch `iss` = FHIR base) | JHE `auth.sof.trusted_issuers` (id_token `iss`) |
  |---|---|---|
  | Epic sandbox | `https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4` | `https://fhir.epic.com/interconnect-fhir-oauth/oauth2` |
  | Medplum | `https://api.medplum.com/fhir/R4` | `https://api.medplum.com/` |
  | Your Epic | your production R4 base, from your Epic admin | your Epic OIDC issuer |

  JHE validates the id_token's own issuer against `auth.sof.trusted_issuers`; put the
  right-hand column value there. (`JHE_TRUSTED_ISS` in `.env` is accepted for backward
  compatibility but current JHE ignores it.)
- `EHR_IFRAME_ORIGIN` — only used by EHRs that **iframe-embed** the app (e.g. Epic); the CSP
  allows that origin to embed it. Redirect-style launches (Medplum) ignore it — see below.
- `MRN_IDENTIFIER_SYSTEM` — the EHR `Patient.identifier` system that holds the MRN
- `JHE_DATA_TYPE_CODES` (optional) — JSON to override the data-type → OMH code map.
  **Note:** the `steps` code default (`omh:step-count:3.0`) is provisional; set it to
  whatever your ingestion path (Garmin shim / Validic) actually emits.
- `NOTEBOOK_DIR` (optional) — the server root, the directory holding `dashboard.ipynb`.
  Defaults to the directory of `jupyter_server_config.py`; the Docker image sets
  `/app/notebooks`.

## Run locally
```
docker compose up --build
```
Then complete a SMART launch from your EHR test environment (or MedPlum dev instance)
pointed at `https://<host>/smart-on-fhir/launch`.

## Deploy
A `Dockerfile` and `fly.toml.example` are provided. Any container host works. On fly.io:

1. Set the issuer allowlist **before** deploying. An app upgraded without it restart-loops
   on `allowed_issuers must list at least one EHR issuer`:
   ```
   fly secrets set -a <app> SMART_ALLOWED_ISSUERS="<FHIR base(s)>"
   ```
2. Deploy on exactly one machine. Sessions live in server memory, so a second machine makes
   callbacks fail with "launch expired" 400s that look like cookie blocking:
   ```
   fly deploy --ha=false
   ```
   (or, for an app that already has two machines, `fly scale count 1`).
3. A deploy or restart ends every session; clinicians relaunch from the chart.

## The iframe / CSP gotcha — only for iframe-embedding EHRs (e.g. Epic)
**This applies only if your EHR embeds the app in an iframe** (e.g. Epic in Hyperspace).
EHRs that launch by **redirecting** the browser to the app — including **Medplum** — render
the app as a normal top-level page, so there's no iframe, this gotcha never applies, and
`EHR_IFRAME_ORIGIN` is unused. (Likewise, the HTTP-vs-HTTPS mixed-content block only bites an
*embedded* frame, not a redirect.)

When the EHR *does* iframe-embed: Voilà and Jupyter default to
`Content-Security-Policy: frame-ancestors 'self'`, which blocks the embed and shows a blank
frame. `jupyter_server_config.py` sets the header from `EHR_IFRAME_ORIGIN` in your `.env`:
```
frame-ancestors 'self' <EHR_IFRAME_ORIGIN>
```
If an embedding EHR shows a blank frame, set `EHR_IFRAME_ORIGIN` to the EHR's origin and
verify the response `Content-Security-Policy` header includes it (DevTools → Network → the
document response). Add more origins as space-separated values. An HTTPS EHR also can't embed
an `http://` app (mixed content) — serve the app over HTTPS in that case.

## Access control and trust boundary
The EHR launch is the only way in; there is no separate login.

- **Who gets in.** Only a browser that completed a SMART launch from an issuer in
  `SMART_ALLOWED_ISSUERS`. The app issues that browser a signed, `HttpOnly` session cookie
  and stores the OAuth state, PKCE verifier and token server-side against it. Any other
  browser gets **403** on the render URL and on every API and kernel route, *before* any
  kernel starts. A launch from any other issuer is refused before the app contacts it.
- **What a session can do.** Load the dashboard and exchange widget messages with the
  kernel Voilà started for it. It **cannot run code**: the kernel connection drops
  `execute_request` (only widget comm messages pass), so the only code that ever runs is
  the committed notebook. It cannot list or attach to other sessions' kernels, use the
  file API (Voilà's tree route still lists notebook names), read the notebook source, or
  open a terminal (terminals are disabled). In the Docker image the server runs as an
  unprivileged user with the app directory read-only.
  Locally (`make run`) the server root is the project directory, so any notebook in it is
  renderable by a launched session; the Docker image narrows the root to `/app/notebooks`
  via `NOTEBOOK_DIR`.
- **What remains, stated plainly.** (1) Widget messages: a session can send any comm
  message its own kernel's widgets accept; the default dashboard registers none.
  (2) Voilà's own kernel-shutdown route checks login only, so a session that somehow learns
  another session's kernel id (random, never listed) could stop that kernel: a nuisance,
  not a data exposure. (3) All kernels still run as one OS user, so one server is still
  one trust domain by design. (4) `/metrics` (Prometheus) is readable by any launched
  session; it is not authorizer-guarded and holds no PHI.
- **Sizing.** Each rendered dashboard holds a kernel (~100 MB+). A session's kernels are
  shut down when the session ends (relaunch, logout, expiry), and idle kernels are culled
  after 10 minutes. The tab's unload beacon only works where the `_xsrf` cookie is accepted
  (top-level launches, not the EHR iframe). A 1 GB VM supports a handful of concurrent
  sessions.
- **Trust boundary.** **One standalone server is one trust domain**: suitable for a single
  organization's clinic team or a pilot, where every launcher is an authorized user of the
  same EHR and the EHR audits each launch. For multiple organizations or large user
  populations run the same app under JupyterHub, which gives each clinician their own
  server. If a container is ever compromised, rotate `JHE_CLIENT_SECRET`.
- **Demo vs production.** Keep separate instances: a demo that trusts the Epic sandbox
  would otherwise admit anyone with public sandbox credentials.
- **Sessions expire** with the EHR token's `expires_in` (cap `SMARTExtensionApp.session_lifetime`,
  default 1 h); expired token files are removed along with their kernels.
  `/logout` clears the server-side session only; it does not revoke the EHR token.
- **One session per browser.** A new launch replaces the previous session in that browser.
  Each render URL names its session, so an older frame fails closed (403) instead of
  showing another patient. Relaunch it from its chart.
- **Cookies in the EHR iframe.** The cookie is `Secure; SameSite=None; Partitioned` on
  https, which works inside Epic Hyperspace. If a browser still blocks it you get a
  "your browser may be blocking third-party cookies" page; fix by registering the app to
  open in a new window, or allowing cookies for the app's site. Partitioned cookies:
  Chrome/Edge 114+, Firefox 141+, Safari 26.2+. Always serve the app over **https**.
- **Single machine.** Sessions live in server memory: run one machine (`fly scale count 1`),
  and note that a deploy or restart ends every session (relaunch from the chart). See
  [Deploy](#deploy) for the exact commands.
