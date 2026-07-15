# Jupyter server configuration for the SoF provider app.
# Loads the SMART-on-FHIR launch extension and Voilà in one server.
import os

from dotenv import load_dotenv

# Load .env so these settings — and the notebook kernel, which inherits this env — see it.
load_dotenv()

c.ServerApp.jpserver_extensions = {  # noqa: F821
    "jupyter_smart_on_fhir": True,
    "voila": True,
}

# --- SMART on FHIR launch (jupyter-smart-on-fhir) ---
# client_id/scopes come from .env; fallbacks are neutral placeholders. Public client + PKCE.
c.SMARTExtensionApp.client_id = os.environ.get("SMART_CLIENT_ID", "00000000-0000-0000-0000-000000000000")  # noqa: F821
c.SMARTExtensionApp.scopes = os.environ.get("SMART_SCOPES", "openid fhirUser launch patient/*.read").split()  # noqa: F821

# --- Reverse proxy / https fronting ---
# Behind an https proxy or tunnel (fly.io, cloudflared, ngrok) the OAuth
# redirect_uri must be built with the PUBLIC scheme+host, not the container's.
# Trust X-Forwarded-* from the proxy; SMART_REDIRECT_URI overrides explicitly.
c.ServerApp.trust_xheaders = True  # noqa: F821
if os.environ.get("SMART_REDIRECT_URI"):
    c.SMARTExtensionApp.redirect_uri = os.environ["SMART_REDIRECT_URI"]  # noqa: F821

# --- Authentication ---
# The SMART/OAuth flow IS the auth layer. Disable Jupyter's own token/password login, else
# the EHR launch (which carries no Jupyter token) bounces to /login.
# POC single-session model — see docs/deployment.md before exposing this publicly.
c.ServerApp.token = ""  # noqa: F821
c.ServerApp.password = ""  # noqa: F821

# --- Voilà (renders dashboard.ipynb as the provider-facing app) ---
c.VoilaConfiguration.file_allowlist = ["dashboard.ipynb"]  # noqa: F821
c.VoilaConfiguration.strip_sources = True  # noqa: F821
c.VoilaConfiguration.theme = "light"  # noqa: F821

# EHR launch carries no 'next', so point the server root at the Voilà-rendered notebook.
c.ServerApp.default_url = "/voila/render/dashboard.ipynb"  # noqa: F821

# --- Embed in the EHR iframe ---
# Default frame-ancestors 'self' blocks EHR embedding; allow the configured origin(s).
c.ServerApp.tornado_settings = {  # noqa: F821
    "headers": {
        "Content-Security-Policy": "frame-ancestors 'self' " + os.environ.get("EHR_IFRAME_ORIGIN", "https://app.medplum.com")
    }
}
