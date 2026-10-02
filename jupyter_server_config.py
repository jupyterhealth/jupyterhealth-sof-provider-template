# Jupyter server configuration for the SoF provider app.
# Loads the SMART-on-FHIR launch extension and Voilà in one server.

import os

from dotenv import load_dotenv

c = get_config()  # noqa

# Load .env so these settings — and the notebook kernel, which inherits this env — see it.
load_dotenv()

c.ServerApp.jpserver_extensions = {
    "jupyter_smart_on_fhir": True,
    "voila": True,
}

# --- SMART on FHIR launch (jupyter-smart-on-fhir) ---
# client_id/scopes come from .env; fallbacks are neutral placeholders. Public client + PKCE.
c.SMARTExtensionApp.client_id = os.environ.get(
    "SMART_CLIENT_ID", "00000000-0000-0000-0000-000000000000"
)
c.SMARTExtensionApp.scopes = os.environ.get(
    "SMART_SCOPES", "openid fhirUser launch patient/*.read"
).split()

# --- Reverse proxy / https fronting ---
# Behind an https proxy or tunnel (fly.io, cloudflared, ngrok) the OAuth
# redirect_uri must be built with the PUBLIC scheme+host, not the container's.
# Trust X-Forwarded-* from the proxy; SMART_REDIRECT_URI overrides explicitly.
c.ServerApp.trust_xheaders = True
if os.environ.get("SMART_REDIRECT_URI"):
    c.SMARTExtensionApp.redirect_uri = os.environ["SMART_REDIRECT_URI"]

# --- Authentication ---
# The SMART/OAuth flow IS the auth layer.
# This authenticator ensures that every Jupyter request is authorized by the SMART launch.
c.ServerApp.identity_provider_class = (
    "jupyter_smart_on_fhir.server_extension.SMARTIdentityProvider"
)

# --- Voilà (renders dashboard.ipynb as the provider-facing app) ---
c.VoilaConfiguration.file_allowlist = ["dashboard.ipynb"]
c.VoilaConfiguration.strip_sources = True
c.VoilaConfiguration.theme = "light"

# EHR launch carries no 'next', so point the server root at the Voilà-rendered notebook.
c.ServerApp.default_url = "/voila/render/dashboard.ipynb"

# --- Embed in the EHR iframe ---
# Default frame-ancestors 'self' blocks EHR embedding; allow the configured origin(s).
c.ServerApp.tornado_settings = {
    "headers": {
        "Content-Security-Policy": "frame-ancestors 'self' "
        + os.environ.get("EHR_IFRAME_ORIGIN", "https://app.medplum.com")
    }
}
