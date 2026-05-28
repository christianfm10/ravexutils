import asyncio
import contextlib
from typing import Any

import aiohttp
import pytest
from aiohttp import web

from shared_lib.baseclient.endpoint import Endpoint
from shared_lib.baseclient.ws_client import WebSocketClient


@pytest.mark.asyncio
async def test_reconnect_after_server_disconnect() -> None:
    connection_count = 0
    second_connection_event = asyncio.Event()

    async def ws_handler(request: web.Request) -> web.WebSocketResponse:
        nonlocal connection_count

        ws = web.WebSocketResponse()
        await ws.prepare(request)
        connection_count += 1

        if connection_count == 1:
            # Force a non-clean close so the client triggers its reconnect flow.
            await ws.close(code=aiohttp.WSCloseCode.GOING_AWAY, message=b"disconnect")
            return ws

        second_connection_event.set()

        async for _ in ws:
            pass

        return ws

    app = web.Application()
    app.router.add_get("/ws", ws_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()

    server = site._server
    assert server is not None
    sockets = server.sockets  # type: ignore
    assert sockets is not None and sockets
    port = sockets[0].getsockname()[1]
    ws_url = f"ws://127.0.0.1:{port}/ws"

    class _TestWebSocketClient(WebSocketClient):
        ENDPOINT = Endpoint.from_url(ws_url)

        def __init__(self) -> None:
            super().__init__(heartbeat=1)
            self.notifications: list[str] = []

        async def _message_handler(self, message: str) -> None:
            return None

        async def _send_notification(self, message: str) -> None:
            self.notifications.append(message)

        async def _build_subscribe_message(
            self, method: str, **kwargs: Any
        ) -> dict[str, Any]:
            return {"method": method, **kwargs}

        async def _build_unsubscribe_message(
            self, method: str, **kwargs: Any
        ) -> dict[str, Any]:
            return {"method": method, **kwargs}

    client = _TestWebSocketClient()
    client._reconnect_delay_seconds = 0.05
    client._max_reconnect_attempts = 2

    start_task = asyncio.create_task(client.start())

    try:
        await asyncio.wait_for(second_connection_event.wait(), timeout=5)
        assert connection_count >= 2
    finally:
        if not start_task.done():
            start_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await start_task

        # await asyncio.sleep(0)
        await client.close()
        await runner.cleanup()


@pytest.mark.asyncio
async def test_reconnect_fails_after_max_attempts() -> None:
    connection_count = 0
    first_disconnect_event = asyncio.Event()

    async def ws_handler(request: web.Request) -> web.WebSocketResponse:
        nonlocal connection_count

        ws = web.WebSocketResponse()
        await ws.prepare(request)
        connection_count += 1

        # Always close with a reconnect-eligible code to force retries.
        await ws.close(code=aiohttp.WSCloseCode.GOING_AWAY, message=b"disconnect")
        first_disconnect_event.set()
        return ws

    app = web.Application()
    app.router.add_get("/ws", ws_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()

    server = site._server
    assert server is not None
    sockets = server.sockets  # type: ignore
    assert sockets is not None and sockets
    port = sockets[0].getsockname()[1]
    ws_url = f"ws://127.0.0.1:{port}/ws"

    class _TestWebSocketClient(WebSocketClient):
        ENDPOINT = Endpoint.from_url(ws_url)

        def __init__(self) -> None:
            super().__init__(heartbeat=1)
            self.notifications: list[str] = []

        async def _message_handler(self, message: str) -> None:
            return None

        async def _send_notification(self, message: str) -> None:
            self.notifications.append(message)

        async def _build_subscribe_message(
            self, method: str, **kwargs: Any
        ) -> dict[str, Any]:
            return {"method": method, **kwargs}

        async def _build_unsubscribe_message(
            self, method: str, **kwargs: Any
        ) -> dict[str, Any]:
            return {"method": method, **kwargs}

    client = _TestWebSocketClient()
    client._reconnect_delay_seconds = 0.05
    client._max_reconnect_attempts = 2

    start_task = asyncio.create_task(client.start())

    try:
        # Wait until initial disconnect happens, then stop server to force
        # reconnect attempts to fail with connection errors.
        await asyncio.wait_for(first_disconnect_event.wait(), timeout=5)
        await runner.cleanup()

        # start() should end once reconnect attempts are exhausted.
        await asyncio.wait_for(start_task, timeout=5)

        assert connection_count >= 1
        assert client._is_reconnecting is False
    finally:
        await client.close()

        # Runner may already be cleaned during the test body.
        with contextlib.suppress(Exception):
            await runner.cleanup()

        if not start_task.done():
            start_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await start_task
