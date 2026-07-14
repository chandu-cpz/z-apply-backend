from __future__ import annotations

import asyncio

import pytest

from z_apply_backend.services.vnc_bridge import VncBridge


class _FakeWebSocket:
    def __init__(self, *, token_valid: bool = True) -> None:
        self.accepted = False
        self.closed: tuple[int, str] | None = None
        self.sent: list[bytes] = []
        self._server_sent = asyncio.Event()
        self._receive_count = 0
        self.token_valid = token_valid

    async def accept(self) -> None:
        self.accepted = True

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed = (code, reason)

    async def receive(self) -> dict[str, object]:
        self._receive_count += 1
        if self._receive_count == 1:
            return {"type": "websocket.receive", "bytes": b"client-data"}
        await self._server_sent.wait()
        return {"type": "websocket.disconnect"}

    async def send_bytes(self, data: bytes) -> None:
        self.sent.append(data)
        self._server_sent.set()


@pytest.mark.asyncio
async def test_bridge_reuses_access_for_same_vnc_endpoint_and_rotates_for_new_one() -> None:
    bridge = VncBridge()
    first = await bridge.issue_access("127.0.0.1", 5900)
    same = await bridge.issue_access("127.0.0.1", 5900)
    changed = await bridge.issue_access("127.0.0.1", 5901)

    assert same.token == first.token
    assert changed.token != first.token


@pytest.mark.asyncio
async def test_bridge_rejects_unknown_token_before_opening_vnc() -> None:
    bridge = VncBridge()
    await bridge.issue_access("127.0.0.1", 5900)
    websocket = _FakeWebSocket()

    await bridge.bridge(websocket, "wrong-token")  # type: ignore[arg-type]

    assert not websocket.accepted
    assert websocket.closed == (1008, "invalid VNC access token")


@pytest.mark.asyncio
async def test_bridge_proxies_binary_data_in_both_directions() -> None:
    class FakeWriter:
        def __init__(self) -> None:
            self.data = bytearray()
            self.written = asyncio.Event()

        def write(self, data: bytes) -> None:
            self.data.extend(data)
            self.written.set()

        async def drain(self) -> None:
            return

        def close(self) -> None:
            return

        async def wait_closed(self) -> None:
            return

    class FakeReader:
        def __init__(self, writer: FakeWriter) -> None:
            self.writer = writer
            self.calls = 0

        async def read(self, _size: int) -> bytes:
            self.calls += 1
            if self.calls == 1:
                return b"RFB 003.008\n"
            await self.writer.written.wait()
            return b""

    writer = FakeWriter()
    reader = FakeReader(writer)

    async def open_connection(_host: str, _port: int) -> tuple[FakeReader, FakeWriter]:
        return reader, writer

    original = asyncio.open_connection
    asyncio.open_connection = open_connection  # type: ignore[assignment]
    bridge = VncBridge()
    access = await bridge.issue_access("127.0.0.1", 5900)
    websocket = _FakeWebSocket()
    try:
        await bridge.bridge(websocket, access.token)  # type: ignore[arg-type]
    finally:
        asyncio.open_connection = original

    assert websocket.accepted
    assert websocket.sent == [b"RFB 003.008\n"]
    assert writer.data == b"client-data"
