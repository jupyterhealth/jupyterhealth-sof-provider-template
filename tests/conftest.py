import pytest

# Keep tests hermetic: clear the app's runtime env vars before each test so a
# developer's real .env or exported shell vars (e.g. JHE_TRUSTED_ISS) can't leak
# in and break assertions about default behavior. Tests set what they need.
_APP_ENV_VARS = (
    "JHE_URL",
    "JHE_TRUSTED_ISS",
    "JHE_DATA_TYPE_CODES",
    "MRN_IDENTIFIER_SYSTEM",
    "SMART_TOKEN_DIR",
    "HTTP_COOKIE",
    "SMART_CLIENT_ID",
    "SMART_SCOPES",
    "EHR_IFRAME_ORIGIN",
)


@pytest.fixture(autouse=True)
def _isolate_app_env(monkeypatch):
    for var in _APP_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
