# JupyterHealth SoF Provider App

A SMART on FHIR **provider-launch** application backed by the JupyterHealth Exchange
(JHE). Launched from an EHR via SMART on FHIR, it resolves the launched patient to a JHE
record **by MRN**, fetches their device data, and renders it via a Voilà-served Jupyter notebook.
You add analytics/viz by editing one notebook cell.

This is a **template repository** — you run it in place; there is no generation step.

## Start a new project from this template

Pick one:

- **GitHub (easiest):** click **Use this template → Create a new repository** — you get a
  fresh repo (new history) with all files copied into your account.
- **CLI:** `gh repo create my-org/acme-provider-app --template the-commons-project/jupyterhealth-sof-provider-template --private`
- **Local, no GitHub repo:** `npx degit the-commons-project/jupyterhealth-sof-provider-template acme-provider-app`
- **Or just** `git clone` this repo.

Then configure and run:

```
python3 -m venv .venv && source .venv/bin/activate   # isolate deps (avoids system-Python errors)
cp .env.example .env     # then fill in the 5 values below — or: make init (interactive)
pip install -e .         # or skip the venv + install and use: docker compose up --build
make run                 # serve the dashboard with Voilà (or: docker compose up --build)
```

> macOS/Homebrew Python is "externally managed" and `pip install` fails (PEP 668) unless you
> install into a virtualenv — hence the `python3 -m venv` step above. Keep it activated for
> `pip`, `make`, and `pytest`. Docker (`docker compose up --build`) needs no venv.

The importable package stays `provider_app` and the served notebook is always
`dashboard.ipynb` — you don't rename anything. Customize by editing `dashboard.ipynb`,
or `cp examples/cgm-dashboard.ipynb dashboard.ipynb` for the CGM showcase.

## Configure `.env` — what each value is and where it comes from

`.env` is gitignored; the app reads it at runtime, so edits take effect on the next run.
`.env.example` ships placeholder values — never commit real values to it.

**From your EHR (Epic, Medplum, …) — where the app launches:**
- `EHR_IFRAME_ORIGIN` — only needed if your EHR **embeds the app in an iframe** (e.g. Epic).
  Redirect-style launches like **Medplum** render the app as a top-level page and ignore it,
  so the default is fine. When it does apply, set it to that EHR's web origin for the CSP — a
  blank frame usually means it's wrong; see `docs/deployment.md`.
- `SMART_CLIENT_ID` — the **`client_id`** from registering this app as a SMART app at your
  EHR (public client + PKCE; no secret). You can register *after* cloning and paste the
  real value later — a placeholder works until then.
- `MRN_IDENTIFIER_SYSTEM` — which **`Patient.identifier` system** holds the MRN. Set this
  same system + value on your test patient in the EHR. See `docs/ehr-registration.md` §3.
- `SMART_SCOPES` — the SMART scopes to request at launch (the default is usually fine).

**From your JupyterHealth Exchange (JHE) instance — where the data lives:**
- `JHE_URL` — its **base URL** (e.g. `https://jhe.fly.dev`). Must exactly match the JHE
  instance's `SITE_URL` (the token-exchange audience check is an exact-match).
- `JHE_CLIENT_ID` / `JHE_CLIENT_SECRET` — the app's **JHE confidential client** credentials
  for the token exchange (JHE's seed registers "SoF EHR Launch" with dev-only defaults;
  rotate for real deployments). The exchange runs server-side, so the secret stays there.
- A **patient with data** whose **external identifier** (the MRN) equals the EHR patient's
  identifier *value* — that equality is the join key between the two systems.
- JHE configured to **trust your EHR** so it accepts the id_token exchange (the app reads
  data with the token it mints at launch — no separate JHE token). See `docs/QUICKSTART.md`.

> The app mints its JHE token at launch by exchanging the EHR id_token (RFC 8693), so
> there is no JHE token to paste — auth is the SMART launch plus the app's JHE client
> credentials.

## Where to start
- **`docs/QUICKSTART.md`** — **start here.** End-to-end: configure the id_token exchange,
  simulate a SMART launch (MedPlum or fully local), and see data on screen.
- **`dashboard.ipynb`** — edit the cell marked `ADD YOUR ANALYTICS + VISUALIZATION`. The
  cells above it (launch context + data fetch) are scaffolded; you normally don't touch them.
- **`provider_app/`** — launch context, MRN→JHE resolution, identity guard, and data fetch.
- **`docs/deployment.md`** — configure, run, deploy, and the iframe/CSP gotcha.
- **`docs/ehr-registration.md`** — register the app with your EHR and start security review.

## Examples

`examples/` holds drop-in replacements for the root `dashboard.ipynb` — copy one over
to start from a richer notebook instead of the generic scaffold. See
[`examples/README.md`](examples/README.md) for details and reproducible demo values.

- **`cgm-dashboard.ipynb`** — a Continuous Glucose Monitoring report (AGP percentile chart,
  glycemic metrics, Time-in-Range) plus an interactive multi-signal showcase (glucose
  overlaid with sleep, activity, and overnight vitals). Use it with
  `cp examples/cgm-dashboard.ipynb dashboard.ipynb`.

## Develop
```
python3 -m venv .venv && source .venv/bin/activate   # if you haven't already
pip install -e ".[test]"       # editable install + test deps (pytest, nbformat)
docker compose up --build      # run; complete a SMART launch from your EHR / MedPlum
pytest                         # unit tests + an end-to-end smoke test against fakes
```
All config is read from `.env` at runtime, so edits take effect on the next run — no code
changes. In Jupyter Lab the launch context isn't present, so `launch_context.current()`
will raise; iterate on visuals with the smoke-test fakes pattern (see `tests/test_smoke.py`).

## Built on
- [`jupyter-smart-on-fhir`](https://github.com/jupyterhealth/jupyter-smart-on-fhir) (SMART launch)
- [`jupyterhealth-client`](https://github.com/jupyterhealth/jupyterhealth-client) (JHE Read API)
- [Voilà](https://voila.readthedocs.io/) (notebook → web app)

## Scope
Generic infrastructure (a POC scaffold). It targets **one provider session at a time** —
see the concurrency note in `docs/deployment.md`. You own clinical analytics, EHR
registration, security review, production deployment, and concurrent-provider hardening.
