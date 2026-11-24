"""A stand-in for the Switch WebSocket, scripted per connection.

Each script is a list of steps played on one incoming connection:
- a dict is sent as a frame,
- ("expect", type) waits for a client message of that type,
- ("close",) closes the socket (the client should reconnect).
When a script runs out the server keeps the socket open, as a quiet stream would.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlparse

from websockets.asyncio.server import ServerConnection, serve


@dataclass
class Opened:
    path: str
    query: dict[str, str]
    authorization: str | None


@dataclass
class FakeSwitch:
    scripts: list[list[Any]]
    opened: list[Opened] = field(default_factory=list)
    received: list[dict[str, Any]] = field(default_factory=list)
    endpoint: str = ""

    async def __aenter__(self) -> "FakeSwitch":
        self._server = await serve(self._handle, "127.0.0.1", 0)
        port = self._server.sockets[0].getsockname()[1]
        self.endpoint = f"http://127.0.0.1:{port}"
        return self

    async def __aexit__(self, *exc: object) -> None:
        self._server.close()
        await self._server.wait_closed()

    async def _handle(self, ws: ServerConnection) -> None:
        url = urlparse(ws.request.path)
        self.opened.append(
            Opened(
                path=url.path,
                query={k: v[0] for k, v in parse_qs(url.query).items()},
                authorization=ws.request.headers.get("Authorization"),
            )
        )
        index = len(self.opened) - 1
        script = self.scripts[index] if index < len(self.scripts) else []
        for step in script:
            if isinstance(step, dict):
                await ws.send(json.dumps(step))
            elif step[0] == "expect":
                while True:
                    message = json.loads(await ws.recv())
                    self.received.append(message)
                    if message.get("type") == step[1]:
                        break
            elif step[0] == "close":
                await ws.close()
                return
        await ws.wait_closed()  # stay open until either side closes


def state(generation: int = 1, cursor: int | None = None) -> dict[str, Any]:
    return {
        "event": "connection_state",
        "data": {
            "generation": generation,
            "cursor": cursor,
            "heartbeat_interval_seconds": 10.0,
            "server": {"version": "test"},
        },
    }


def message(seq: int, body: str, room: str = "room-1") -> dict[str, Any]:
    return {
        "event": "message",
        "id": seq,
        "data": {
            "type": "message",
            "room_id": room,
            "payload": {"addressed": True, "body": body, "sender_name": "zeynep"},
        },
    }
