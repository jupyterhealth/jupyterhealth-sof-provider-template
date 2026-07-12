#!/usr/bin/env bash
# Interactive .env writer — restores the "answer a few prompts" UX after you copy
# this template. Idempotent and non-destructive: refuses to overwrite an existing .env.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -f .env ]; then
  echo ".env already exists — not overwriting. Edit it directly, or delete it and re-run."
  exit 0
fi

if [ ! -f .env.example ]; then
  echo "ERROR: .env.example not found." >&2
  exit 1
fi

echo "Creating .env from .env.example. Press Enter to accept the [default] shown."
echo

prompt() {
  # prompt VAR "Description" "default"
  local var="$1" desc="$2" default="$3" reply
  read -r -p "$desc [$default]: " reply
  printf '%s=%s\n' "$var" "${reply:-$default}"
}

{
  echo "# Local config for THIS deployment — gitignored, do NOT commit."
  prompt JHE_URL               "JupyterHealth Exchange base URL"            "https://jhe.example.org"
  prompt JHE_CLIENT_ID         "JHE confidential client id for the token exchange" "sof-ehr-launch"
  prompt JHE_CLIENT_SECRET     "JHE confidential client secret"             "sof-ehr-launch-dev-secret"
  prompt SMART_CLIENT_ID       "SMART client_id from your EHR app registration" "00000000-0000-0000-0000-000000000000"
  prompt SMART_SCOPES          "SMART scopes (space-separated)"             "openid fhirUser launch patient/*.read"
  prompt EHR_IFRAME_ORIGIN     "EHR web origin that embeds this app (CSP)"  "https://app.medplum.com"
  prompt MRN_IDENTIFIER_SYSTEM "FHIR Patient.identifier system holding the MRN" "https://example.org/mrn"
} > .env

echo
echo "Wrote .env. Confirm JHE trusts your EHR issuer, then run: make run"
