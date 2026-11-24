import asyncio
import json

import httpx
import pytest

from fake_switch import FakeSwitch, message, state
from triager.switch_client import (
    PROTOCOL_SPEAKS,
    Evicted,
    OperationError,
    Refused,
    SwitchClient,
)


def make_client(endpoint: str, **kwargs) -> SwitchClient:
    return SwitchClient(endpoint, "agent-1", "test-token", reconnect_delays=(0,), **kwargs)


async def take(client: SwitchClient, n: int, timeout: float = 5):
    events = []

    async def run():
        stream = client.events()
        try:
            async for event in stream:
                events.append(event)
                if len(events) == n:
                    return
        finally:
            await stream.aclose()  # closes the socket

    await asyncio.wait_for(run(), timeout)
    return events


async def test_opens_the_socket_with_its_declaration_and_token():
    async with FakeSwitch([[state(), message(1, "hello")]]) as switch:
        client = make_client(switch.endpoint)
        [event] = await take(client, 1)

    opened = switch.opened[0]
    assert opened.path == "/agents/agent-1/connection/ws"
    assert opened.authorization == "Bearer test-token"
    assert opened.query["connection_id"] == client.state.connection_id
    assert opened.query["scope"] == "all"
    assert opened.query["filter"] == "addressed"
    assert opened.query["protocol"] == str(PROTOCOL_SPEAKS)
    assert "start_from" not in opened.query
    assert event.type == "message"
    assert event.room_id == "room-1"
    assert event.payload["body"] == "hello"


async def test_answers_ping_with_pong_carrying_the_cursor():
    script = [state(), message(7, "first"), {"event": "ping", "data": {}}, ("expect", "pong"),
              message(8, "after the pong")]
    async with FakeSwitch([script]) as switch:
        events = await take(make_client(switch.endpoint), 2)

    assert switch.received == [{"type": "pong", "cursor": 7}]
    assert [e.seq for e in events] == [7, 8]


async def test_transport_frames_are_not_handed_to_the_agent():
    script = [state(), {"event": "keepalive", "data": {}}, {"event": "gap", "data": {"room_id": "r"}},
              message(1, "real")]
    async with FakeSwitch([script]) as switch:
        events = await take(make_client(switch.endpoint), 2)

    assert [e.type for e in events] == ["gap", "message"]


async def test_reconnects_with_the_same_id_and_resumes_after_the_last_event():
    first = [state(generation=3), message(41, "before the drop"), ("close",)]
    second = [state(generation=3), message(42, "after the drop")]
    async with FakeSwitch([first, second]) as switch:
        client = make_client(switch.endpoint)
        events = await take(client, 2)

    assert [e.payload["body"] for e in events] == ["before the drop", "after the drop"]
    reopened = switch.opened[1].query
    assert reopened["connection_id"] == switch.opened[0].query["connection_id"]
    assert reopened["start_from"] == "41"
    assert reopened["expected_generation"] == "3"


async def test_a_lapsed_heartbeat_eviction_reconnects():
    first = [state(), {"event": "evicted", "data": {"code": "heartbeat_lapsed", "reason": "late"}}]
    second = [state(), message(1, "back")]
    async with FakeSwitch([first, second]) as switch:
        [event] = await take(make_client(switch.endpoint), 1)

    assert event.payload["body"] == "back"
    assert len(switch.opened) == 2


async def test_being_taken_over_is_final():
    script = [state(), {"event": "evicted", "data": {"code": "taken_over", "reason": "another client"}}]
    async with FakeSwitch([script]) as switch:
        with pytest.raises(Evicted, match="taken_over"):
            await take(make_client(switch.endpoint), 1)


async def test_a_refusal_is_raised_not_retried():
    script = [{"event": "refused", "data": {"status": 409, "detail": {"remedy": "update switch-core"}}}]
    async with FakeSwitch([script]) as switch:
        with pytest.raises(Refused) as info:
            await take(make_client(switch.endpoint), 1)

    assert info.value.status == 409
    assert len(switch.opened) == 1


# -- operations -------------------------------------------------------------


def ops_client(handler) -> SwitchClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return SwitchClient("http://switch.test", "agent-1", "test-token", http=http)


async def test_call_posts_arguments_on_the_connection():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["Authorization"]
        seen["connection"] = request.headers["X-Switch-Connection-Id"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"result": {"message_id": "m1"}})

    client = ops_client(handler)
    result = await client.call("post_message", room_id="room-1", body="hi")

    assert result == {"message_id": "m1"}
    assert seen["url"] == "http://switch.test/agents/agent-1/ops/post_message"
    assert seen["auth"] == "Bearer test-token"
    assert seen["connection"] == client.state.connection_id
    assert seen["body"] == {"room_id": "room-1", "body": "hi"}


async def test_a_refused_operation_raises_with_the_servers_reason():
    client = ops_client(lambda r: httpx.Response(409, json={"detail": "connection is not open"}))

    with pytest.raises(OperationError) as info:
        await client.call("run_template", template_id="t1")

    assert info.value.status == 409
    assert info.value.detail == "connection is not open"


async def test_lists_operations():
    ops = [{"name": "post_message", "parameters": {}}]
    client = ops_client(lambda r: httpx.Response(200, json={"operations": ops}))

    assert await client.list_operations() == ops
