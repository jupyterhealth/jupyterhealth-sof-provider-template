"""With XSRF checks ON (as in production), Voilà's unload beacon can shut down the
session's own kernel: the _xsrf cookie is set where the beacon can read and send it."""

from http.cookies import SimpleCookie

import pytest

from tests.test_access_control import (  # noqa: F401
    complete_launch,
    fakes,
    load_real_config,
    notebook,
)


@pytest.fixture
def jp_server_config(tmp_path, jp_root_dir, monkeypatch):
    return load_real_config(
        tmp_path, jp_root_dir, monkeypatch
    )  # disable_check_xsrf stays False


def xsrf_cookie(responses):
    for response in responses:
        for header in response.headers.get_list("Set-Cookie"):
            if header.startswith("_xsrf="):
                jar = SimpleCookie()
                jar.load(header)
                return jar["_xsrf"].coded_value, header
    return None, None


async def test_unload_beacon_shuts_down_own_kernel(jp_fetch, jp_serverapp, notebook):  # noqa: F811
    assert jp_serverapp.disable_check_xsrf is False
    seen = []
    cookie, sid = await complete_launch(jp_fetch, responses=seen)
    r = await jp_fetch(
        "voila",
        "render",
        "dashboard.ipynb",
        params={"smart_session": sid},
        headers={"Cookie": cookie},
        raise_error=False,
        request_timeout=120,
    )
    assert r.code == 200, r.body[:500]
    # The library sets _xsrf on the callback; the render does not set it again.
    xsrf, header = xsrf_cookie([*seen, r])
    assert xsrf, [x.headers.get_list("Set-Cookie") for x in (*seen, r)]
    lowered = header.lower()
    assert (
        "httponly" not in lowered and "secure" in lowered and "samesite=none" in lowered
    )
    km = jp_serverapp.kernel_manager
    (kid,) = list(km.list_kernel_ids())

    r = await jp_fetch(
        "voila",
        "api",
        "shutdown",
        kid,
        method="POST",
        body=b"",
        headers={"Cookie": f"{cookie}; _xsrf={xsrf}", "X-XSRFToken": xsrf},
        raise_error=False,
    )
    assert r.code in (200, 204), r.body[:500]  # Voilà's handler answers 204 No Content
    assert list(km.list_kernel_ids()) == []
