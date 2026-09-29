"""An httpx transport that sends requests through the Workers `fetch` API.

The app's weather / FX / places adapters use synchronous `httpx.Client`. Workers have no raw
outbound sockets for arbitrary HTTPS, but `pyodide.ffi.run_sync` can wait on a JS promise from
synchronous code, so the adapters keep their code and only the transport changes.
"""

from __future__ import annotations

import httpx
from js import AbortSignal, Object, fetch  # type: ignore[import-not-found]
from pyodide.ffi import run_sync, to_js  # type: ignore[import-not-found]

# Hop-by-hop or runtime-owned headers the Workers fetch sets itself.
_DROP_REQUEST = {"host", "content-length", "connection", "accept-encoding", "transfer-encoding"}
# fetch already decoded the body, so these would make httpx decode or size-check it twice.
_DROP_RESPONSE = {"content-encoding", "content-length", "transfer-encoding"}


class FetchTransport(httpx.BaseTransport):
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        init: dict = {
            "method": request.method,
            "headers": [[k, v] for k, v in request.headers.multi_items() if k.lower() not in _DROP_REQUEST],
        }
        body = request.read()
        if body:
            init["body"] = to_js(body)
        timeout = (request.extensions.get("timeout") or {}).get("read")
        if timeout:
            init["signal"] = AbortSignal.timeout(int(timeout * 1000))
        try:
            response = run_sync(fetch(str(request.url), to_js(init, dict_converter=Object.fromEntries)))
            content = run_sync(response.arrayBuffer()).to_bytes()
        except Exception as exc:  # noqa: BLE001 — network errors arrive as JS exceptions
            raise httpx.ConnectError(str(exc), request=request) from exc
        headers = [(k, v) for k, v in response.headers.entries() if k.lower() not in _DROP_RESPONSE]
        return httpx.Response(response.status, headers=headers, content=content, request=request)


def install() -> None:
    """Make every `httpx.Client` created afterwards default to the fetch transport."""
    original = httpx.Client.__init__

    def init(self: httpx.Client, *args, **kwargs) -> None:
        kwargs.setdefault("transport", FetchTransport())
        original(self, *args, **kwargs)

    httpx.Client.__init__ = init  # type: ignore[method-assign]
