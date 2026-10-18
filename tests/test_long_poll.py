"""Long-poll (gateway #182, hub ADR 014): an agent may ask the relay to hold each poll."""

import asyncio
import os
import sys
import time
import unittest

from fake_gateway import OK_HELLO, FakeGateway, bounded, error

from grok_gadgets_linux import Agent, Device

TOKEN = "fixture-agent-token-only"
GATEWAY_SOURCE = os.environ.get("GROK_GATEWAY_SOURCE")


def device():
    return Device("linux-test", "test", simulated=True)


async def run(respond, *, until, **options):
    gateway = await FakeGateway(respond).start()
    agent = Agent(device(), TOKEN, port=gateway.port, poll_interval=0.01, **options)
    stop = asyncio.Event()
    task = asyncio.create_task(agent.run(stop))
    try:
        async with asyncio.timeout(5):
            while not until(agent, gateway) and not task.done():
                await asyncio.sleep(0.01)
    finally:
        stop.set()
        await asyncio.wait_for(task, 5)
        await gateway.close()
    return agent, gateway


class LongPollTests(unittest.IsolatedAsyncioTestCase):
    def test_wait_ms_must_be_100_to_10000(self):
        for bad in (99, 10001, 2.5, True, "2500"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                Agent(device(), TOKEN, wait_ms=bad)
        Agent(device(), TOKEN, wait_ms=2500)

    @bounded()
    async def test_polls_carry_wait_ms_only_when_asked(self):
        def respond(message, connection):
            return OK_HELLO if message["type"] == "hello" else {"ok": True, "commands": []}

        def polls(gateway):
            return [m for m in gateway.received if m["type"] == "poll"]

        _, plain = await run(respond, until=lambda a, g: len(polls(g)) >= 2)
        self.assertTrue(all("wait_ms" not in m for m in polls(plain)))
        _, waiting = await run(respond, until=lambda a, g: len(polls(g)) >= 2, wait_ms=500)
        self.assertTrue(all(m["wait_ms"] == 500 for m in polls(waiting)))

    @bounded()
    async def test_an_older_relay_keeps_the_session_and_the_field_is_dropped(self):
        def respond(message, connection):
            if message["type"] == "hello":
                return OK_HELLO
            if message["type"] == "poll" and "wait_ms" in message:
                return error("invalid_request")
            return {"ok": True, "commands": []} if message["type"] == "poll" else {"ok": True}

        def bare(gateway):
            return [m for m in gateway.received if m == {"type": "poll"}]

        agent, gateway = await run(respond, until=lambda a, g: len(bare(g)) >= 3, wait_ms=500)
        self.assertEqual((agent.sessions, gateway.connections), (1, 1))
        asked = [m for m in gateway.received if m.get("wait_ms")]
        self.assertEqual(len(asked), 1)  # Asked once, then never again until restart.


@unittest.skipUnless(GATEWAY_SOURCE, "Set GROK_GATEWAY_SOURCE to the gateway's src")
class LongPollGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_waiting_poll_gets_a_command_at_once(self):
        import json
        import tempfile
        from pathlib import Path

        sys.path.insert(0, GATEWAY_SOURCE)
        from grok_gadgets_gateway.domain import Gateway
        from grok_gadgets_gateway.transport import Credentials, DeviceServer

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "credentials.json"
            path.write_text(json.dumps({"devices": {"linux-test": {"token": TOKEN}}}))
            path.chmod(0o600)
            gateway = Gateway()
            server = await DeviceServer(gateway, Credentials(path), port=0).start()
            lamp = device()
            calls = []
            lamp.capability("custom.set", lambda arguments: calls.append(arguments) or {})
            agent = Agent(lamp, TOKEN, port=server.port, wait_ms=5000)
            stop = asyncio.Event()
            task = asyncio.create_task(agent.run(stop))
            try:
                await asyncio.wait_for(agent.connected.wait(), 2)
                await asyncio.sleep(0.5)  # The agent is now inside a waiting poll.
                started = time.monotonic()
                command = gateway.command("linux-test", "custom.set", {"v": 1})
                async with asyncio.timeout(3):
                    while gateway.command_status(command["command_id"])["status"] != "executed":
                        await asyncio.sleep(0.01)
                self.assertLess(time.monotonic() - started, 1.5)
            finally:
                stop.set()
                await asyncio.wait_for(task, 8)
                await asyncio.wait_for(server.close(), 5)
