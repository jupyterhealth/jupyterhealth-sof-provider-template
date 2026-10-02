"""Loads the REAL jupyter_server_config.py into a test server and proves: without a
session the render URL and every API route are refused before any kernel starts; with a
session from a faked launch the dashboard renders exactly one kernel and that kernel
reads its own token."""

import asyncio
import json
import os
import sys
import uuid
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

import nbformat
import pytest
from tornado.httpclient import HTTPClientError
from traitlets.config.loader import PyFileConfigLoader

from jupyter_smart_on_fhir import server_extension as ext
from jupyter_smart_on_fhir.server_extension import SMARTCallbackHandler, callback_path, launch_path, login_path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ISS = "https://ehr.example/fhir"
COOKIE = "smart-session"


@pytest.fixture
def jp_server_config(tmp_path, jp_root_dir, monkeypatch):
    # The real config calls load_dotenv(); it never overrides variables already set, so set
    # ours first. JUPYTER_PATH lets Voilà find its templates under pytest-jupyter.
    monkeypatch.setenv("SMART_ALLOWED_ISSUERS", ISS)
    monkeypatch.setenv("SMART_CLIENT_ID", "test-client")
    monkeypatch.setenv("NOTEBOOK_DIR", str(jp_root_dir))
    monkeypatch.setenv("JUPYTER_PATH", os.path.join(sys.prefix, "share", "jupyter"))
    c = PyFileConfigLoader("jupyter_server_config.py", path=str(PROJECT_ROOT)).load_config()
    c.ServerApp.disable_check_xsrf = True
    c.SMARTExtensionApp.token_dir = str(tmp_path / "sessions")
    c.SMARTExtensionApp.token_file = str(tmp_path / "legacy.json")
    return c


@pytest.fixture
def notebook(jp_root_dir, tmp_path):
    """A one-cell dashboard that proves the kernel can read its own session token."""
    out = tmp_path / "token_seen.txt"
    nb = nbformat.v4.new_notebook()
    nb.cells.append(nbformat.v4.new_code_cell(
        "from jupyter_smart_on_fhir.session import load_token\n"
        f"open({str(out)!r}, 'w').write(load_token()['token']['access_token'])\n"
        "print('rendered')"
    ))
    nbformat.write(nb, jp_root_dir / "dashboard.ipynb")
    return out


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    async def fetch_discovery_document(iss, timeout):
        return {"token_endpoint": "https://ehr.example/token", "authorization_endpoint": "https://ehr.example/authorize"}

    async def token_for_code(self, code, code_verifier, token_url):
        return {"access_token": "AT-RENDER", "token_type": "Bearer", "id_token": "IDT", "patient": "P1", "expires_in": 900}

    monkeypatch.setattr(ext, "fetch_discovery_document", fetch_discovery_document)
    monkeypatch.setattr(SMARTCallbackHandler, "token_for_code", token_for_code)


def cookie_header(response) -> str:
    hits = [h for h in response.headers.get_list("Set-Cookie") if h.startswith(f"{COOKIE}=")]
    assert len(hits) == 1
    jar = SimpleCookie()
    jar.load(hits[0])
    return f"{COOKIE}={jar[COOKIE].coded_value}"


async def complete_launch(jp_fetch):
    l = await jp_fetch(launch_path, params={"iss": ISS, "launch": "L1"}, follow_redirects=False, raise_error=False)
    assert l.code == 302, l.body
    cookie = cookie_header(l)
    q = dict(parse_qsl(urlparse(l.headers["Location"]).query))
    lg = await jp_fetch(login_path, params=q, headers={"Cookie": cookie}, follow_redirects=False, raise_error=False)
    assert lg.code == 302, lg.body
    state = dict(parse_qsl(urlparse(lg.headers["Location"]).query))["state"]
    cb = await jp_fetch(callback_path, params={"code": "C1", "state": state}, headers={"Cookie": cookie},
                        follow_redirects=False, raise_error=False)
    assert cb.code == 302, cb.body
    return cookie, dict(parse_qsl(urlparse(cb.headers["Location"]).query))["smart_session"]


def test_real_config_wires_everything(jp_serverapp, jp_server_config, jp_root_dir):
    from jupyter_smart_on_fhir.server_extension import SMARTAuthorizer, SMARTIdentityProvider

    assert isinstance(jp_serverapp.identity_provider, SMARTIdentityProvider)
    assert isinstance(jp_serverapp.authorizer, SMARTAuthorizer)
    assert jp_serverapp.allow_unauthenticated_access is False
    assert jp_serverapp.reraise_server_extension_failures is True
    assert jp_serverapp.terminals_enabled is False
    assert jp_serverapp.web_app.settings["smart_allowed_issuers"] == {ISS}
    km = jp_serverapp.kernel_manager
    assert km.cull_idle_timeout == 3600 and km.cull_connected is True
    assert km.cull_interval == 300
    assert km.allowed_message_types == [
        "comm_open", "comm_close", "comm_msg", "comm_info_request", "kernel_info_request", "shutdown_request",
    ]
    # Voilà keeps its config on the handler kwargs, not in settings; assert the loaded Config.
    c = jp_server_config
    assert c.ServerApp.root_dir == str(jp_root_dir)
    assert c.VoilaConfiguration.http_header_envs == ["Cookie"]
    assert c.VoilaConfiguration.file_allowlist == [] and c.VoilaConfiguration.strip_sources is True
    assert not (PROJECT_ROOT / "voila.json").exists()  # it would re-apply file_allowlist after this config
    text = (PROJECT_ROOT / "jupyter_server_config.py").read_text()
    assert 'ServerApp.token = ""' not in text and 'ServerApp.password = ""' not in text
    assert jp_serverapp.web_app.settings["extra_log_scrub_param_keys"] == ["smart_session", "launch"]


def test_root_dir_defaults_to_config_directory(monkeypatch):
    monkeypatch.delenv("NOTEBOOK_DIR", raising=False)
    monkeypatch.setenv("SMART_ALLOWED_ISSUERS", ISS)
    c = PyFileConfigLoader("jupyter_server_config.py", path=str(PROJECT_ROOT)).load_config()
    assert c.ServerApp.root_dir == str(PROJECT_ROOT)


async def test_render_without_session_is_refused_before_kernel_start(jp_fetch, jp_serverapp, notebook):
    r = await jp_fetch("voila", "render", "dashboard.ipynb", follow_redirects=False, raise_error=False)
    assert r.code == 302 and "/login" in r.headers["Location"]
    r = await jp_fetch("login", raise_error=False)
    assert r.code == 403 and "must be opened from your EHR" in r.body.decode()
    assert list(jp_serverapp.kernel_manager.list_kernel_ids()) == []
    assert not notebook.exists()


async def test_notebook_source_is_not_served_to_anyone(jp_fetch, notebook):
    assert (await jp_fetch("voila", "files", "dashboard.ipynb", raise_error=False)).code in (403, 404)
    cookie, _ = await complete_launch(jp_fetch)
    r = await jp_fetch("voila", "files", "dashboard.ipynb", headers={"Cookie": cookie}, raise_error=False)
    assert r.code in (403, 404)


def _msg(msg_type, content=None):
    return json.dumps({
        "header": {"msg_id": uuid.uuid4().hex, "msg_type": msg_type, "username": "t",
                   "session": uuid.uuid4().hex, "version": "5.3", "date": "2026-10-01T00:00:00Z"},
        "parent_header": {}, "metadata": {}, "content": content or {}, "channel": "shell", "buffers": [],
    })


async def _reply_types(ws, seconds=3.0):
    seen = []
    try:
        while True:
            raw = await asyncio.wait_for(ws.read_message(), seconds)
            if raw is None:
                break
            if isinstance(raw, str):
                seen.append(json.loads(raw)["header"]["msg_type"])
    except asyncio.TimeoutError:
        pass
    return seen


async def test_api_without_session_is_refused(jp_fetch, jp_serverapp):
    assert (await jp_fetch("api", "kernels", raise_error=False)).code == 403
    assert (await jp_fetch("api", "contents", raise_error=False)).code == 403
    assert list(jp_serverapp.kernel_manager.list_kernel_ids()) == []


async def test_render_with_session_runs_one_kernel_that_reads_its_own_token(
    jp_fetch, jp_ws_fetch, jp_serverapp, notebook, tmp_path, caplog
):
    cookie, sid = await complete_launch(jp_fetch)
    r = await jp_fetch("voila", "render", "dashboard.ipynb", params={"smart_session": sid},
                       headers={"Cookie": cookie}, raise_error=False, request_timeout=120)
    assert r.code == 200, r.body[:500]
    assert "rendered" in r.body.decode()
    kids = list(jp_serverapp.kernel_manager.list_kernel_ids())
    assert len(kids) == 1
    assert notebook.read_text() == "AT-RENDER"
    kid = kids[0]

    # Own kernel: REST read allowed, comm/kernel_info allowed, execute_request DROPPED.
    assert (await jp_fetch("api", "kernels", kid, headers={"Cookie": cookie}, raise_error=False)).code == 200
    ws = await jp_ws_fetch("api", "kernels", kid, "channels", headers={"Cookie": cookie})
    ws.write_message(_msg("kernel_info_request"))
    assert "kernel_info_reply" in await _reply_types(ws)
    pwned = tmp_path / "pwned"
    ws.write_message(_msg("execute_request", {"code": f"open({str(pwned)!r}, 'w')", "silent": True,
                                              "store_history": False, "user_expressions": {},
                                              "allow_stdin": False, "stop_on_error": True}))
    assert "execute_reply" not in await _reply_types(ws)
    assert not pwned.exists()
    assert "which is not allowed" in caplog.text
    ws.close()

    # Another authenticated session (a second launch from a different browser) is refused
    # on this kernel over REST and over the websocket.
    other_cookie, _ = await complete_launch(jp_fetch)
    assert (await jp_fetch("api", "kernels", kid, headers={"Cookie": other_cookie}, raise_error=False)).code == 403
    with pytest.raises(HTTPClientError) as exc:
        await jp_ws_fetch("api", "kernels", kid, "channels", headers={"Cookie": other_cookie})
    assert exc.value.code == 403
    assert len(list(jp_serverapp.kernel_manager.list_kernel_ids())) == 1  # nothing extra started


async def test_render_url_for_another_session_fails_closed(jp_fetch, jp_serverapp, notebook):
    cookie, _ = await complete_launch(jp_fetch)
    r = await jp_fetch("voila", "render", "dashboard.ipynb", params={"smart_session": "q" * 32},
                       headers={"Cookie": cookie}, follow_redirects=False, raise_error=False)
    assert r.code == 302 and "/login" in r.headers["Location"]
    assert list(jp_serverapp.kernel_manager.list_kernel_ids()) == []


async def test_session_cannot_use_api_surfaces(jp_fetch):
    cookie, _ = await complete_launch(jp_fetch)
    for path in (("api", "kernels"), ("api", "contents"), ("api", "sessions")):
        assert (await jp_fetch(*path, headers={"Cookie": cookie}, raise_error=False)).code == 403, path
    assert (await jp_fetch("api", "terminals", headers={"Cookie": cookie}, raise_error=False)).code in (403, 404)
