import httpx
import pytest
import respx

from app.websearch.client import (
    SearxngClient, WebResult, WebSearchError, sanitise_text, sanitise_url,
)

BASE = "http://searx.test"


def make_client(**kw) -> SearxngClient:
    kw.setdefault("timeout", 1.0)
    kw.setdefault("max_results", 5)
    kw.setdefault("backoff", 0)
    return SearxngClient(BASE, **kw)


def hit(url="https://a.example/x", title="T", content="S", engine="duckduckgo"):
    return {"url": url, "title": title, "content": content, "engine": engine}


# --- sanitising -----------------------------------------------------------------------------------

def test_sanitise_text_strips_tags_scripts_and_collapses_whitespace():
    raw = "Hello <b>world</b>\n\n  <script>alert(1)</script>  <style>p{}</style> &amp; more\t!"
    assert sanitise_text(raw, 300) == "Hello world & more !"


def test_sanitise_text_handles_none_and_non_string():
    assert sanitise_text(None, 10) == ""
    assert sanitise_text(123, 10) == ""


def test_sanitise_text_truncates():
    assert sanitise_text("x" * 400, 300) == "x" * 300
    assert sanitise_text("  " + "y" * 200 + "  ", 160) == "y" * 160


def test_sanitise_text_drops_unterminated_tag_and_comment():
    assert sanitise_text("ok <!-- hidden --> text <img src=x onerror=1", 100) == "ok text"


def test_sanitise_text_unterminated_script_is_removed():
    assert sanitise_text("before <script>evil()", 100) == "before"


@pytest.mark.parametrize("url", ["javascript:alert(1)", "data:text/html,x", "ftp://x.example/a", "file:///etc/passwd",
                                 "//x.example", "not a url", "", None, 5, "http://", "JAVASCRIPT:alert(1)"])
def test_sanitise_url_rejects_dangerous(url):
    assert sanitise_url(url) is None


def test_sanitise_url_accepts_http_and_https():
    assert sanitise_url(" https://a.example/p?q=1 ") == "https://a.example/p?q=1"
    assert sanitise_url("HTTP://a.example/") == "HTTP://a.example/"


def test_sanitise_url_rejects_overlong_and_whitespace_inside():
    assert sanitise_url("https://a.example/" + "a" * 3000) is None
    assert sanitise_url("https://a.example/a b") is None


def test_web_result_to_dict():
    assert WebResult("t", "https://a.example/", "s", "e").to_dict() == {
        "title": "t", "url": "https://a.example/", "snippet": "s", "engine": "e"}


# --- search ---------------------------------------------------------------------------------------

@respx.mock
async def test_search_success_parses_and_sends_params():
    route = respx.get(f"{BASE}/search").respond(json={"results": [
        hit(title="<i>Delhi</i> demand", content="Big <script>x()</script> growth", engine="bing"),
    ]})
    results = await make_client().search("del bom demand")
    assert results == [WebResult(title="Delhi demand", url="https://a.example/x", snippet="Big growth", engine="bing")]
    params = route.calls.last.request.url.params
    assert params["q"] == "del bom demand"
    assert params["format"] == "json" and params["language"] == "en" and params["safesearch"] == "1"


@respx.mock
async def test_search_drops_dangerous_urls_dedupes_and_caps():
    items = [hit("javascript:alert(1)"), hit("data:text/html,x"), hit("https://a.example/1"),
             hit("https://a.example/1", title="dup")]
    items += [hit(f"https://b.example/{i}") for i in range(10)]
    respx.get(f"{BASE}/search").respond(json={"results": items})
    results = await make_client(max_results=3).search("q")
    assert [r.url for r in results] == ["https://a.example/1", "https://b.example/0", "https://b.example/1"]
    assert results[0].title == "T"  # first wins


@respx.mock
async def test_search_skips_malformed_entries_and_handles_missing_fields():
    respx.get(f"{BASE}/search").respond(json={"results": [
        "str", None, 5, {"title": "no url"}, {"url": "https://ok.example/"},
        {"url": "https://t.example/", "title": None, "content": None, "engine": None},
    ]})
    results = await make_client().search("q")
    assert [r.url for r in results] == ["https://ok.example/", "https://t.example/"]
    assert results[0].title == "" and results[0].snippet == "" and results[0].engine == ""


@respx.mock
async def test_search_empty_results_ok():
    respx.get(f"{BASE}/search").respond(json={"results": []})
    assert await make_client().search("q") == []


@pytest.mark.parametrize("body", [{"nope": 1}, {"results": "x"}, [1, 2], "str", None])
@respx.mock
async def test_search_bad_shape_raises(body):
    respx.get(f"{BASE}/search").respond(json=body)
    with pytest.raises(WebSearchError):
        await make_client().search("q")


@respx.mock
async def test_search_malformed_json_raises():
    respx.get(f"{BASE}/search").respond(content=b"<html>not json")
    with pytest.raises(WebSearchError, match="invalid JSON"):
        await make_client().search("q")


@respx.mock
async def test_search_5xx_then_success_retries():
    route = respx.get(f"{BASE}/search").mock(side_effect=[
        httpx.Response(503), httpx.Response(200, json={"results": [hit()]}),
    ])
    assert len(await make_client().search("q")) == 1
    assert route.call_count == 2


@respx.mock
async def test_search_retries_exhausted_after_three_attempts():
    route = respx.get(f"{BASE}/search").respond(500)
    with pytest.raises(WebSearchError, match="HTTP 500"):
        await make_client().search("q")
    assert route.call_count == 3


@respx.mock
async def test_search_timeout_retries_then_raises():
    route = respx.get(f"{BASE}/search").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(WebSearchError, match="ReadTimeout"):
        await make_client().search("q")
    assert route.call_count == 3


@respx.mock
async def test_search_network_error_then_success():
    respx.get(f"{BASE}/search").mock(side_effect=[
        httpx.ConnectError("down"), httpx.Response(200, json={"results": [hit()]}),
    ])
    assert len(await make_client().search("q")) == 1


@respx.mock
async def test_search_4xx_does_not_retry():
    route = respx.get(f"{BASE}/search").respond(403)
    with pytest.raises(WebSearchError, match="HTTP 403"):
        await make_client().search("q")
    assert route.call_count == 1


@respx.mock
async def test_backoff_sleeps_between_attempts(monkeypatch):
    slept = []

    async def fake_sleep(s):
        slept.append(s)

    monkeypatch.setattr("app.websearch.client.asyncio.sleep", fake_sleep)
    respx.get(f"{BASE}/search").respond(502)
    with pytest.raises(WebSearchError):
        await make_client(backoff=0.5).search("q")
    assert slept == [0.5, 1.0]


@respx.mock
async def test_base_url_trailing_slash_is_tolerated():
    respx.get(f"{BASE}/search").respond(json={"results": []})
    assert await SearxngClient(BASE + "/", timeout=1, max_results=2, backoff=0).search("q") == []


# --- ping -----------------------------------------------------------------------------------------

@respx.mock
async def test_ping_true_on_2xx():
    respx.get(f"{BASE}/healthz").respond(200)
    assert await make_client().ping() is True


@respx.mock
async def test_ping_false_on_error_status_and_network_error():
    respx.get(f"{BASE}/healthz").respond(500)
    assert await make_client().ping() is False
    respx.get(f"{BASE}/healthz").mock(side_effect=httpx.ConnectError("x"))
    assert await make_client().ping() is False
