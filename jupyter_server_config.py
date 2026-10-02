# Jupyter server configuration for the SoF provider app.
# Loads the SMART-on-FHIR launch extension and Voilà in one server.
import os

from dotenv import load_dotenv

# Load .env so these settings — and the notebook kernel, which inherits this env — see it.
load_dotenv()

c.ServerApp.jpserver_extensions = {  # noqa: F821
    "jupyter_smart_on_fhir": True,
    "voila": True,
    "jupyter_server_terminals": False,  # a session must never get a shell
}
c.ServerApp.terminals_enabled = False  # noqa: F821
# Extension errors (e.g. an empty issuer allowlist) must stop the server, not silently
# disable the extension that provides the only authentication.
c.ServerApp.reraise_server_extension_failures = True  # noqa: F821
# Only the dashboard notebook lives under root_dir; nothing else is renderable or listable.
c.ServerApp.root_dir = os.environ.get("NOTEBOOK_DIR", "/app/notebooks")  # noqa: F821

# --- SMART on FHIR launch (jupyter-smart-on-fhir) ---
# client_id/scopes come from .env; fallbacks are neutral placeholders. Public client + PKCE.
c.SMARTExtensionApp.client_id = os.environ.get(
    "SMART_CLIENT_ID", "00000000-0000-0000-0000-000000000000"
)
c.SMARTExtensionApp.scopes = os.environ.get(
    "SMART_SCOPES", "openid fhirUser launch patient/*.read"
).split()
# Only these EHRs may launch the app (the launch `iss`). Required: the server refuses to
# start when empty. Keep in step with JHE's auth.sof.trusted_issuers.
c.SMARTExtensionApp.allowed_issuers = os.environ.get("SMART_ALLOWED_ISSUERS", "").split()

# --- Reverse proxy / https fronting ---
# Behind an https proxy or tunnel (fly.io, cloudflared, ngrok) the OAuth
# redirect_uri must be built with the PUBLIC scheme+host, not the container's.
# Trust X-Forwarded-* from the proxy; SMART_REDIRECT_URI overrides explicitly.
c.ServerApp.trust_xheaders = True  # noqa: F821
if os.environ.get("SMART_REDIRECT_URI"):
    c.SMARTExtensionApp.redirect_uri = os.environ["SMART_REDIRECT_URI"]  # noqa: F821

# --- Authentication + authorization ---
# The EHR launch is the only way in. SMARTIdentityProvider makes "has an authenticated
# SMART session cookie" the definition of a user, so Voilà's render handler and every
# kernel route return 403 before any kernel starts for a browser that did not launch.
# SMARTAuthorizer then lets a session reach only the kernel Voilà started for it.
c.ServerApp.identity_provider_class = (  # noqa: F821
    "jupyter_smart_on_fhir.server_extension.SMARTIdentityProvider"
)
c.ServerApp.authorizer_class = "jupyter_smart_on_fhir.server_extension.SMARTAuthorizer"  # noqa: F821
c.ServerApp.allow_unauthenticated_access = False  # noqa: F821

# A session may exchange widget comm messages with its kernel but never run code: the
# kernel websocket drops execute_request and everything else not listed here (this is the
# same filter standalone Voilà applies; as a server extension it must be set explicitly).
c.MappingKernelManager.allowed_message_types = [  # noqa: F821
    "comm_open",
    "comm_close",
    "comm_msg",
    "comm_info_request",
    "kernel_info_request",
    "shutdown_request",
]
# Kernels outlive their session's cookie; reap idle ones.
c.MappingKernelManager.cull_idle_timeout = 3600  # noqa: F821
c.MappingKernelManager.cull_interval = 300  # noqa: F821
c.MappingKernelManager.cull_connected = True  # noqa: F821

# --- Voilà (renders dashboard.ipynb as the provider-facing app) ---
c.VoilaConfiguration.file_allowlist = []  # noqa: F821  — /voila/files must not serve the notebook source
c.VoilaConfiguration.strip_sources = True  # noqa: F821
c.VoilaConfiguration.theme = "light"  # noqa: F821
# The kernel gets the request's Cookie header as $HTTP_COOKIE so it can read only the
# launching browser's own session token (provider_app.launch_context).
c.VoilaConfiguration.http_header_envs = ["Cookie"]  # noqa: F821

# EHR launch carries no 'next', so point the server root at the Voilà-rendered notebook.
c.ServerApp.default_url = "/voila/render/dashboard.ipynb"  # noqa: F821

# --- Embed in the EHR iframe ---
# Default frame-ancestors 'self' blocks EHR embedding; allow the configured origin(s).
c.ServerApp.tornado_settings = {  # noqa: F821
    "headers": {
        "Content-Security-Policy": "frame-ancestors 'self' "
        + os.environ.get("EHR_IFRAME_ORIGIN", "https://app.medplum.com")
    }
}
