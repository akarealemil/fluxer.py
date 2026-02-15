from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any, Callable, Coroutine

import aiohttp

from .enums import GatewayCloseCode, GatewayOpcode, Intents
from .errors import GatewayNotConnected

log = logging.getLogger(__name__)


class GatewayPayload:
    """Represents a Gateway payload (sent or received).

    All gateway messages follow this structure:
        op: opcode (int)
        d:  event data (dict, int, or None)
        s:  sequence number (only for op 0 DISPATCH)
        t:  event name (only for op 0 DISPATCH)
    """

    __slots__ = ("op", "d", "s", "t")

    def __init__(
        self, op: int, d: Any = None, s: int | None = None, t: str | None = None
    ):
        self.op = op
        self.d = d
        self.s = s
        self.t = t

    @classmethod
    def from_json(cls, raw: str) -> GatewayPayload:
        data = json.loads(raw)
        return cls(op=data["op"], d=data.get("d"), s=data.get("s"), t=data.get("t"))

    def to_json(self) -> str:
        payload: dict[str, Any] = {"op": self.op, "d": self.d}
        if self.s is not None:
            payload["s"] = self.s
        if self.t is not None:
            payload["t"] = self.t
        return json.dumps(payload)

    def __repr__(self) -> str:
        op_name = (
            GatewayOpcode(self.op).name
            if self.op in GatewayOpcode.__members__.values()
            else str(self.op)
        )
        return f"<GatewayPayload op={op_name} t={self.t!r} s={self.s}>"


class Gateway:
    """Manages the WebSocket connection to the Fluxer Gateway.

    This class handles the full lifecycle: connect, heartbeat, identify,
    dispatch events, and reconnect on failure.
    """

    def __init__(
        self,
        *,
        http_client: Any,
        token: str,
        intents: Intents,
        dispatch: Callable[[str, Any], Coroutine[Any, Any, None]],
    ) -> None:
        self._http = http_client
        self._token = token
        self._intents = intents
        self._dispatch = dispatch

        # Connection state
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self._heartbeat_interval: float = 41.25
        self._sequence: int | None = None
        self._session_id: str | None = None
        self._resume_gateway_url: str | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._is_closed: bool = False
        self._last_heartbeat_ack: bool = True

        self._tasks = []

    @property
    def is_connected(self) -> bool:
        return self._ws is not None and not self._ws.closed

    async def connect(self) -> None:
        """Establish the gateway connection and enter the event loop."""
        gateway_data = await self._http.get_gateway_bot()
        gateway_url = gateway_data["url"]
        ws_url = f"{gateway_url}?v=1&encoding=json"

        log.info("Connecting to gateway: %s", ws_url)

        self._session = aiohttp.ClientSession()
        self._is_closed = False

        while not self._is_closed:
            try:
                await self._connect_and_run(ws_url)
            except (
                aiohttp.WSServerHandshakeError,
                aiohttp.ClientError,
                asyncio.TimeoutError,
            ) as e:
                log.warning("Gateway connection error: %s. Reconnecting in 5s...", e)
                await asyncio.sleep(5)
            except Exception as e:
                log.error("Unexpected gateway error: %s", e, exc_info=True)
                await asyncio.sleep(5)

    async def _connect_and_run(self, url: str) -> None:
        """Single connection attempt: connect, handshake, then listen."""
        connect_url = self._resume_gateway_url or url
        if self._resume_gateway_url:
            connect_url = f"{self._resume_gateway_url}?v=1&encoding=json"

        assert self._session is not None
        self._ws = await self._session.ws_connect(connect_url, max_msg_size=0)
        log.info("WebSocket connected")

        try:
            await self._event_loop()
        finally:
            self._stop_heartbeat()
            if self._ws and not self._ws.closed:
                await self._ws.close()

    async def _event_loop(self) -> None:
        """Main receive loop: read messages and handle opcodes."""
        if self._ws is None:
            raise GatewayNotConnected("WebSocket connection not established")

        async for msg in self._ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                payload = GatewayPayload.from_json(msg.data)
                await self._handle_payload_task(payload)

            elif msg.type == aiohttp.WSMsgType.BINARY:
                payload = GatewayPayload.from_json(msg.data.decode("utf-8"))
                await self._handle_payload_task(payload)

            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
                log.info("WebSocket closing")
                break

            elif msg.type == aiohttp.WSMsgType.ERROR:
                log.error("WebSocket error: %s", self._ws.exception())
                break

        if self._ws.close_code:
            await self._handle_close_code(self._ws.close_code)

    async def _handle_payload_task(self, payload: GatewayPayload) -> None:
        """Simple wrapper function to ensure that gateway payload handling is done truly asynchronously"""
        task = asyncio.create_task(self._handle_payload(payload))
        self._tasks.append(task)
        task.add_done_callback(lambda t: self._tasks.remove(t))
        task.add_done_callback(lambda t: t.result())
    
    async def _handle_payload(self, payload: GatewayPayload) -> None:
        """Route an incoming payload by opcode."""
        log.debug("Received: %s", payload)

        match payload.op:
            case GatewayOpcode.HELLO:
                self._heartbeat_interval = payload.d["heartbeat_interval"] / 1000.0
                self._start_heartbeat()

                if self._session_id:
                    await self._send_resume()
                else:
                    await self._send_identify()

            case GatewayOpcode.HEARTBEAT_ACK:
                self._last_heartbeat_ack = True
                log.debug("Heartbeat ACK received")

            case GatewayOpcode.HEARTBEAT:
                await self._send_heartbeat()

            case GatewayOpcode.DISPATCH:
                if payload.s is not None:
                    self._sequence = payload.s

                event_name = payload.t or ""
                await self._handle_dispatch(event_name, payload.d)

            case GatewayOpcode.RECONNECT:
                log.info("Gateway requested reconnect")
                if self._ws:
                    await self._ws.close()

            case GatewayOpcode.INVALID_SESSION:
                resumable = payload.d if isinstance(payload.d, bool) else False
                log.warning("Invalid session (resumable=%s)", resumable)
                if not resumable:
                    self._session_id = None
                    self._sequence = None
                    self._resume_gateway_url = None
                await asyncio.sleep(1 + (5 * (not resumable)))
                if self._ws:
                    await self._ws.close()

    async def _handle_dispatch(self, event_name: str, data: Any) -> None:
        """Handle a DISPATCH event (op 0)."""
        match event_name:
            case "READY":
                self._session_id = data["session_id"]
                self._resume_gateway_url = data.get("resume_gateway_url")
                log.info(
                    "READY: session=%s, user=%s",
                    self._session_id,
                    data["user"].get("username", "?"),
                )

            case "RESUMED":
                log.info("Successfully resumed session")

        await self._dispatch(event_name, data)

    async def _handle_close_code(self, code: int) -> None:
        """Handle a WebSocket close code from the gateway."""
        log.info("Gateway closed with code %d", code)

        try:
            close_code = GatewayCloseCode(code)
            if not close_code.is_reconnectable:
                log.error(
                    "Fatal close code %d (%s), not reconnecting", code, close_code.name
                )
                self._is_closed = True
        except ValueError:
            # Unknown close code, try to reconnect
            log.warning("Unknown close code %d, attempting reconnect", code)

    # =========================================================================
    # Sending
    # =========================================================================

    async def _send(self, payload: GatewayPayload) -> None:
        """Send a payload over the WebSocket."""
        if self._ws is None or self._ws.closed:
            log.warning("Tried to send on closed WebSocket")
            return
        raw = payload.to_json()
        log.debug("Sending: %s", payload)
        await self._ws.send_str(raw)

    async def _send_identify(self) -> None:
        """Send the IDENTIFY payload to start a new session."""
        payload = GatewayPayload(
            op=GatewayOpcode.IDENTIFY,
            d={
                "token": self._token,
                "intents": int(self._intents),
                "properties": {
                    "os": sys.platform,
                    "browser": "fluxer.py",
                    "device": "fluxer.py",
                },
            },
        )
        await self._send(payload)
        log.info("Sent IDENTIFY")

    async def _send_resume(self) -> None:
        """Send the RESUME payload to continue an existing session."""
        payload = GatewayPayload(
            op=GatewayOpcode.RESUME,
            d={
                "token": self._token,
                "session_id": self._session_id,
                "seq": self._sequence,
            },
        )
        await self._send(payload)
        log.info("Sent RESUME (session=%s, seq=%s)", self._session_id, self._sequence)

    async def _send_heartbeat(self) -> None:
        """Send a heartbeat to keep the connection alive."""
        payload = GatewayPayload(op=GatewayOpcode.HEARTBEAT, d=self._sequence)
        await self._send(payload)

    # =========================================================================
    # Heartbeat loop
    # =========================================================================

    def _start_heartbeat(self) -> None:
        self._stop_heartbeat()
        self._last_heartbeat_ack = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    def _stop_heartbeat(self) -> None:
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

    async def _heartbeat_loop(self) -> None:
        """Periodically send heartbeats. If we miss an ACK, reconnect."""
        try:
            import random

            await asyncio.sleep(self._heartbeat_interval * random.random())
            while True:
                if not self._last_heartbeat_ack:
                    log.warning(
                        "Missed heartbeat ACK, closing connection to trigger reconnect"
                    )
                    if self._ws and not self._ws.closed:
                        await self._ws.close(code=4000)
                    return

                self._last_heartbeat_ack = False
                await self._send_heartbeat()
                await asyncio.sleep(self._heartbeat_interval)
        except asyncio.CancelledError:
            pass

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def close(self) -> None:
        """Gracefully close the gateway connection."""
        self._is_closed = True
        self._stop_heartbeat()
        if self._ws and not self._ws.closed:
            await self._ws.close(code=1000)
        if self._session and not self._session.closed:
            await self._session.close()

    async def update_presence(
        self,
        *,
        status: str = "online",
        activity_name: str | None = None,
        activity_type: int = 0,
    ) -> None:
        """Update the bot's presence/status."""
        activity = None
        if activity_name:
            activity = {"name": activity_name, "type": activity_type}

        payload = GatewayPayload(
            op=GatewayOpcode.PRESENCE_UPDATE,
            d={
                "since": None,
                "activities": [activity] if activity else [],
                "status": status,
                "afk": False,
            },
        )
        await self._send(payload)
