"""A client for the Switch agent protocol.

Two channels, as the server defines them (switch_core/bridges/agent):

- Events come down one WebSocket, GET /agents/{id}/connection/ws. Frames are
  JSON {"event", "data", "id"}; `id` is the sequence number a reconnecting
  client passes back as `start_from`. The server sends {"event": "ping"} every
  heartbeat interval and the client answers {"type": "pong", "cursor": n}.
- Operations go up as POST /agents/{id}/ops/{operation}, the arguments as the
  JSON body and X-Switch-Connection-Id naming the open connection. Operation
  names are the MCP tool names.

The connection id is generated here, once, so a reconnect reopens the same
connection and resumes from the last event it saw instead of starting over.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator
from urllib.parse import urlencode

import httpx
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from . import __version__

log = logging.getLogger(__name__)

# Agent-protocol revisions this client implements (server: speaks 9, accepts 8).
PROTOCOL_SPEAKS = 9
PROTOCOL_ACCEPTS = 8
CLIENT_NAME = "bug-to-pr-triager"

# Frames that are about the connection itself, not something the agent acts on.
_TRANSPORT_FRAMES = {"ping", "keepalive", "connection_state", "refused", "evicted"}
# Eviction codes that another reconnect cannot fix.
_FINAL_EVICTIONS = {"taken_over"}


class SwitchError(Exception):
    pass


class Refused(SwitchError):
    """The server refused to open the connection (bad token, version mismatch...)."""

    def __init__(self, status: int, detail: Any):
        super().__init__(f"connection refused ({status}): {detail}")
        self.status = status
        self.detail = detail


class Evicted(SwitchError):
    """The server closed the connection for good, e.g. another client took it over."""

    def __init__(self, code: str, reason: str):
        super().__init__(f"evicted ({code}): {reason}")
        self.code = code
        self.reason = reason


class OperationError(SwitchError):
    def __init__(self, operation: str, status: int, detail: Any):
        super().__init__(f"{operation} failed ({status}): {detail}")
        self.operation = operation
        self.status = status
        self.detail = detail


@dataclass(frozen=True)
class Event:
    """Something that happened in a room: a message, someone joining, a gap."""

    type: str
    data: dict[str, Any]
    seq: int | None = None

    @property
    def room_id(self) -> str | None:
        return self.data.get("room_id")

    @property
    def payload(self) -> dict[str, Any]:
        return self.data.get("payload") or {}


@dataclass
class ConnectionState:
    connection_id: str
    generation: int | None = None
    cursor: int | None = None
    heartbeat_interval: float | None = None
    server: dict[str, Any] = field(default_factory=dict)


class SwitchClient:
    def __init__(
        self,
        endpoint: str,
        agent_id: str,
        token: str,
        *,
        scope: str = "all",
        event_filter: str = "addressed",
        http: httpx.AsyncClient | None = None,
        reconnect_delays: tuple[float, ...] = (1, 2, 5, 10, 30),
    ):
        self.endpoint = endpoint.rstrip("/")
        self.agent_id = agent_id
        self._token = token
        self.scope = scope
        self.event_filter = event_filter
        self.state = ConnectionState(connection_id=str(uuid.uuid4()))
        self._http = http or httpx.AsyncClient(timeout=30)
        self._owns_http = http is None
        self._reconnect_delays = reconnect_delays

    # -- operations ---------------------------------------------------------

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    async def call(self, operation: str, **arguments: Any) -> Any:
        """Run one Switch operation on the open connection and return its result."""
        response = await self._http.post(
            f"{self.endpoint}/agents/{self.agent_id}/ops/{operation}",
            json=arguments,
            headers={**self._headers, "X-Switch-Connection-Id": self.state.connection_id},
        )
        if response.status_code >= 400:
            raise OperationError(operation, response.status_code, _detail(response))
        return response.json().get("result")

    async def list_operations(self) -> list[dict[str, Any]]:
        """Every operation the server offers, with its JSON-schema parameters."""
        response = await self._http.get(
            f"{self.endpoint}/agents/{self.agent_id}/ops", headers=self._headers
        )
        if response.status_code >= 400:
            raise OperationError("list_operations", response.status_code, _detail(response))
        return response.json()["operations"]

    # -- events -------------------------------------------------------------

    def _socket_url(self) -> str:
        params: dict[str, Any] = {
            "connection_id": self.state.connection_id,
            "scope": self.scope,
            "filter": self.event_filter,
            "protocol": PROTOCOL_SPEAKS,
            "protocol_accepts": PROTOCOL_ACCEPTS,
            "client": CLIENT_NAME,
            "client_version": __version__,
        }
        if self.state.cursor is not None:
            params["start_from"] = self.state.cursor
        if self.state.generation is not None:
            params["expected_generation"] = self.state.generation
        base = self.endpoint.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
        return f"{base}/agents/{self.agent_id}/connection/ws?{urlencode(params)}"

    async def events(self) -> AsyncIterator[Event]:
        """Room events, forever. Reconnects on drops and resumes where it left off.

        Raises Refused or Evicted when reconnecting cannot help.
        """
        attempt = 0
        while True:
            try:
                async with connect(self._socket_url(), additional_headers=self._headers) as ws:
                    async for event in self._read(ws):
                        attempt = 0
                        yield event
                # The server ended the stream cleanly; open it again.
            except (ConnectionClosed, OSError) as exc:
                log.warning("switch connection dropped: %s", exc)
            delay = self._reconnect_delays[min(attempt, len(self._reconnect_delays) - 1)]
            attempt += 1
            log.info("reconnecting in %ss from cursor %s", delay, self.state.cursor)
            await asyncio.sleep(delay)

    async def _read(self, ws: ClientConnection) -> AsyncIterator[Event]:
        async for raw in ws:
            frame = json.loads(raw)
            name = frame.get("event")
            data = frame.get("data") or {}
            seq = frame.get("id")

            if name == "ping":
                await ws.send(json.dumps({"type": "pong", "cursor": self.state.cursor}))
            elif name == "connection_state":
                self.state.generation = data.get("generation")
                self.state.heartbeat_interval = data.get("heartbeat_interval_seconds")
                self.state.server = data.get("server") or {}
                if self.state.cursor is None:
                    self.state.cursor = data.get("cursor")
            elif name == "refused":
                raise Refused(data.get("status", 0), data.get("detail"))
            elif name == "evicted":
                code = data.get("code", "closed")
                if code in _FINAL_EVICTIONS:
                    raise Evicted(code, data.get("reason", ""))
                log.warning("evicted (%s), will reconnect: %s", code, data.get("reason"))
                return
            elif name not in _TRANSPORT_FRAMES:
                if seq is not None:
                    self.state.cursor = seq
                yield Event(type=name, data=data, seq=seq)

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()


def _detail(response: httpx.Response) -> Any:
    try:
        return response.json().get("detail")
    except ValueError:
        return response.text
