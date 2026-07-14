from __future__ import annotations

import asyncio
import contextlib
import secrets
from dataclasses import dataclass

from fastapi import WebSocket, WebSocketDisconnect


@dataclass(frozen=True, slots=True)
class VncAccess:
    token: str
    host: str
    port: int


class VncBridge:
    """Token-gated WebSocket-to-TCP bridge for noVNC's RFB connection.

    This is the small subset of websockify that the local single-user product
    needs. It avoids exposing x11vnc directly to the browser or supervising an
    additional daemon process.
    """

    def __init__(self) -> None:
        self._access: VncAccess | None = None
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def issue_access(self, host: str, port: int) -> VncAccess:
        async with self._lock:
            if self._access is None or (self._access.host, self._access.port) != (host, port):
                self._access = VncAccess(secrets.token_urlsafe(32), host, port)
            return self._access

    async def bridge(self, websocket: WebSocket, token: str) -> None:
        async with self._lock:
            access = self._access
        if access is None or not secrets.compare_digest(access.token, token):
            await websocket.close(code=1008, reason="invalid VNC access token")
            return

        try:
            reader, writer = await asyncio.open_connection(access.host, access.port)
        except OSError:
            await websocket.close(code=1011, reason="VNC endpoint unavailable")
            return

        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
        upstream = asyncio.create_task(
            self._websocket_to_vnc(websocket, writer), name="novnc-to-vnc"
        )
        downstream = asyncio.create_task(
            self._vnc_to_websocket(reader, websocket), name="vnc-to-novnc"
        )
        try:
            done, pending = await asyncio.wait(
                (upstream, downstream), return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*done, *pending, return_exceptions=True)
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
            async with self._lock:
                self._connections.discard(websocket)
            with contextlib.suppress(Exception):
                await websocket.close()

    async def close(self) -> None:
        async with self._lock:
            connections = tuple(self._connections)
            self._access = None
        for websocket in connections:
            with contextlib.suppress(Exception):
                await websocket.close(code=1001, reason="backend stopping")

    @staticmethod
    async def _websocket_to_vnc(websocket: WebSocket, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    return
                data = message.get("bytes")
                if data is None and message.get("text") is not None:
                    data = message["text"].encode()
                if data:
                    writer.write(data)
                    await writer.drain()
        except WebSocketDisconnect:
            return

    @staticmethod
    async def _vnc_to_websocket(reader: asyncio.StreamReader, websocket: WebSocket) -> None:
        while data := await reader.read(64 * 1024):
            await websocket.send_bytes(data)
