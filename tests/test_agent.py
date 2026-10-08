import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from fake_gateway import OK_HELLO, FakeGateway, bounded, error

from grok_gadgets_linux import Agent, Device, SDKError

GATEWAY_SOURCE = os.environ.get("GROK_GATEWAY_SOURCE")
if GATEWAY_SOURCE:
    sys.path.insert(0, GATEWAY_SOURCE)
    from grok_gadgets_gateway.domain import Gateway
    from grok_gadgets_gateway.transport import Credentials, DeviceServer

TOKEN = "fixture-agent-token-only"


async def eventually(predicate, timeout=2):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.005)


class AgentUnitTests(unittest.IsolatedAsyncioTestCase):
    def device(self):
        return Device("linux-test", "test", simulated=True).event_capability("button")

    def test_loopback_and_capped_jittered_backoff(self):
        with self.assertRaises(ValueError):
            Agent(self.device(), TOKEN, host="0.0.0.0")
        with self.assertRaises(ValueError):
            Agent(self.device(), TOKEN, reconnect_attempts=0)
        agent = Agent(self.device(), TOKEN, backoff_initial=0.1, backoff_cap=0.5)
        for attempt, ceiling in enumerate([0.1, 0.2, 0.4, 0.5, 0.5, 0.5]):
            delays = {agent.retry_delay(attempt) for _ in range(50)}
            self.assertTrue(all(ceiling / 2 <= delay <= ceiling for delay in delays))
            self.assertGreater(len(delays), 1)

    async def run_against(self, respond, *, device=None, stop_when=None, **options):
        gateway = await FakeGateway(respond).start()
        agent = Agent(
            device or self.device(),
            TOKEN,
            port=gateway.port,
            poll_interval=0.01,
            backoff_initial=0.01,
            backoff_cap=0.02,
            **options,
        )
        stop = asyncio.Event()
        task = asyncio.create_task(agent.run(stop))
        try:
            if stop_when:
                await eventually(lambda: stop_when(agent, gateway) or task.done(), 5)
                stop.set()
            await asyncio.wait_for(task, 5)
        finally:
            stop.set()
            await gateway.close()
        return agent, gateway

    @bounded()
    async def test_one_unauthorized_after_hello_is_retried_then_fatal(self):
        def flaky(message, connection):
            if message["type"] == "hello":
                return OK_HELLO if connection < 3 else error("unauthorized")
            return error("unauthorized") if connection < 3 else {"ok": True}

        with self.assertRaises(SDKError) as caught:
            await self.run_against(flaky)
        self.assertEqual(caught.exception.code, "unauthorized")

        sessions = []

        def recovers(message, connection):
            sessions.append(connection)
            if message["type"] == "state" and connection == 1:
                return error("unauthorized")
            return OK_HELLO if message["type"] == "hello" else {"ok": True, "commands": []}

        agent, _ = await self.run_against(recovers, stop_when=lambda a, g: a.sessions >= 2)
        self.assertEqual((agent.sessions, agent.retries), (2, 1))

    @bounded()
    async def test_unauthorized_before_any_hello_and_revoked_are_immediate(self):
        with self.assertRaises(SDKError) as caught:
            await self.run_against(lambda message, connection: error("unauthorized"))
        self.assertEqual(caught.exception.code, "unauthorized")

        def revoked(message, connection):
            return OK_HELLO if message["type"] == "hello" else error("revoked")

        gateway = await FakeGateway(revoked).start()
        agent = Agent(self.device(), TOKEN, port=gateway.port, poll_interval=0.01)
        try:
            with self.assertRaises(SDKError) as caught:
                await asyncio.wait_for(agent.run(), 2)
        finally:
            await gateway.close()
        self.assertEqual((caught.exception.code, agent.retries), ("revoked", 0))

    @bounded()
    async def test_unavailable_and_busy_are_retryable(self):
        def transient(message, connection):
            if connection <= 2:
                return error("unavailable" if connection == 1 else "busy")
            return OK_HELLO if message["type"] == "hello" else {"ok": True, "commands": []}

        agent, _ = await self.run_against(transient, stop_when=lambda a, g: a.sessions >= 1)
        self.assertEqual(agent.retries, 2)

    @bounded()
    async def test_late_ack_and_unknown_command_replies_keep_the_session(self):
        for code in ("late_ack", "unknown_command"):
            with self.subTest(code=code):
                device = Device("linux-test", "test", simulated=True)
                device.capability("custom.set", lambda arguments: {"v": arguments["v"]})
                pending = [{"command_id": "c1", "capability": "custom.set", "arguments": {"v": 1}}]

                def respond(message, connection, code=code, pending=pending):
                    if message["type"] == "hello":
                        return OK_HELLO
                    if message["type"] == "poll":
                        return {"ok": True, "commands": [pending.pop()] if pending else []}
                    if message["type"] == "ack":
                        return error(code)
                    return {"ok": True}

                agent, gateway = await self.run_against(
                    respond,
                    device=device,
                    stop_when=lambda a, g: a.dropped_acks and len(g.received) > 8,
                )
                self.assertEqual((agent.sessions, agent.retries, gateway.connections), (1, 0, 1))
                self.assertEqual(agent.dropped_acks, 1)

    @bounded()
    async def test_deeply_nested_reply_is_invalid_response(self):
        nested = b"[" * 1020 + b"]" * 1020 + b"\n"
        with self.assertRaises(SDKError) as caught:
            await self.run_against(lambda message, connection: nested)
        self.assertEqual(caught.exception.code, "invalid_response")

    @bounded()
    async def test_stop_cancels_in_flight_handler_then_runs_shutdown_hooks(self):
        markers = []
        started = asyncio.Event()
        device = self.device()

        async def relay(arguments):
            markers.append("relay on")
            started.set()
            try:
                await asyncio.sleep(30)
            finally:
                markers.append("relay off")
            return {}

        device.capability("relay.set", relay)
        device.on_shutdown(lambda: markers.append("safe state"))

        def respond(message, connection):
            if message["type"] == "poll" and "relay on" not in markers:
                return {
                    "ok": True,
                    "commands": [{"command_id": "r1", "capability": "relay.set", "arguments": {}}],
                }
            return OK_HELLO if message["type"] == "hello" else {"ok": True, "commands": []}

        loop = asyncio.get_running_loop()
        began = loop.time()
        _, gateway = await self.run_against(
            respond, device=device, stop_when=lambda a, g: started.is_set()
        )
        self.assertLess(loop.time() - began, 2)
        self.assertEqual(markers, ["relay on", "relay off", "safe state"])
        self.assertNotIn("ack", [message["type"] for message in gateway.received])

    @bounded()
    async def test_retry_forever_does_not_exhaust(self):
        server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        server.close()
        await server.wait_closed()
        agent = Agent(
            self.device(),
            TOKEN,
            port=port,
            reconnect_attempts=None,
            backoff_initial=0.001,
            backoff_cap=0.002,
        )
        stop = asyncio.Event()
        task = asyncio.create_task(agent.run(stop))
        await eventually(lambda: agent.retries > 40 or task.done(), 5)
        self.assertFalse(task.done())
        stop.set()
        await asyncio.wait_for(task, 1)

    async def test_failed_connections_exhaust_and_stop_interrupts_backoff(self):
        server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        server.close()
        await server.wait_closed()
        agent = Agent(
            self.device(),
            TOKEN,
            port=port,
            reconnect_attempts=2,
            backoff_initial=0.01,
            backoff_cap=0.01,
        )
        with self.assertRaises(SDKError) as error:
            await agent.run()
        self.assertEqual(error.exception.code, "reconnect_exhausted")
        self.assertEqual(agent.retries, 2)
        stop = asyncio.Event()
        task = asyncio.create_task(agent.run(stop))
        await asyncio.sleep(0.005)
        stop.set()
        await asyncio.wait_for(task, 1)


@unittest.skipUnless(GATEWAY_SOURCE, "Set GROK_GATEWAY_SOURCE for real gateway integration")
class GatewayIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "credentials.json"
        self.write_credentials()
        self.gateway = Gateway()
        self.server = await DeviceServer(self.gateway, Credentials(self.path), port=0).start()
        self.stop = asyncio.Event()
        self.task = None
        self.calls = []
        self.device = Device("linux-test", "test", simulated=True)

        async def handler(arguments):
            self.calls.append(arguments)
            return {"custom": arguments["value"]}

        self.device.capability(
            "custom.set",
            handler,
            schema={
                "type": "object",
                "properties": {"value": {"type": "integer"}},
                "required": ["value"],
                "additionalProperties": False,
            },
        )
        self.device.event_capability("button")
        self.agent = Agent(
            self.device,
            TOKEN,
            port=self.server.port,
            poll_interval=0.01,
            backoff_initial=0.01,
            backoff_cap=0.02,
        )

    def write_credentials(self, revoked=False):
        self.path.write_text(
            json.dumps({"devices": {"linux-test": {"token": TOKEN, "revoked": revoked}}})
        )
        self.path.chmod(0o600)

    async def start_agent(self):
        self.task = asyncio.create_task(self.agent.run(self.stop))
        await asyncio.wait_for(self.agent.connected.wait(), 1)

    async def asyncTearDown(self):
        self.stop.set()
        try:
            if self.task and not self.task.done():
                await asyncio.wait_for(self.task, 2)
        finally:
            try:
                await asyncio.wait_for(self.server.close(), 5)
            finally:
                self.directory.cleanup()

    async def restart_gateway(self):
        port = self.server.port
        # Bounded: a gateway close that waits on connected agents must fail, not hang.
        await asyncio.wait_for(self.server.close(), 5)
        self.gateway = Gateway()
        self.server = await DeviceServer(self.gateway, Credentials(self.path), port=port).start()
        sessions = self.agent.sessions
        await eventually(lambda: self.agent.sessions > sessions, 5)

    @bounded()
    async def test_reused_id_with_changed_arguments_after_restart_keeps_session(self):
        await self.start_agent()
        self.gateway.command("linux-test", "custom.set", {"value": 1}, "c1")
        await eventually(lambda: self.gateway.command_status("c1")["status"] == "executed")
        await self.restart_gateway()
        sessions = self.agent.sessions
        self.gateway.command("linux-test", "custom.set", {"value": 2}, "c1")
        await eventually(lambda: self.gateway.command_status("c1")["status"] == "failed")
        status = self.gateway.command_status("c1")
        self.assertEqual(status["error"]["code"], "device_failed")
        self.assertEqual(self.calls, [{"value": 1}])
        await asyncio.sleep(0.05)
        self.assertFalse(self.task.done())
        self.assertEqual(self.agent.sessions, sessions)
        self.assertTrue(self.gateway.state("linux-test")["available"])
        self.gateway.command("linux-test", "custom.set", {"value": 3}, "c2")
        await eventually(lambda: self.gateway.command_status("c2")["status"] == "executed")
        self.assertEqual(self.gateway.state("linux-test")["state"], {"custom": 3})

    @bounded()
    async def test_same_id_replay_after_restart_reports_current_state(self):
        await self.start_agent()
        self.gateway.command("linux-test", "custom.set", {"value": 1}, "c1")
        await eventually(lambda: self.gateway.command_status("c1")["status"] == "executed")
        self.gateway.command("linux-test", "custom.set", {"value": 2}, "c2")
        await eventually(lambda: self.gateway.command_status("c2")["status"] == "executed")
        await self.restart_gateway()
        self.gateway.command("linux-test", "custom.set", {"value": 1}, "c1")
        await eventually(lambda: self.gateway.command_status("c1")["status"] == "executed")
        self.assertEqual(self.gateway.command_status("c1")["reported_state"], {"custom": 2})
        self.assertEqual(len(self.calls), 2)

    @bounded()
    async def test_custom_capability_execution_events_and_gateway_dedup(self):
        await self.start_agent()
        self.gateway.command("linux-test", "custom.set", {"value": 7}, "c1")
        await eventually(lambda: self.gateway.command_status("c1")["status"] == "executed")
        self.assertEqual(self.gateway.state("linux-test")["state"], {"custom": 7})
        self.assertFalse(self.gateway.command_status("c1")["physical_verified"])
        self.assertTrue(self.gateway.command_status("c1")["simulated"])
        self.gateway.command("linux-test", "custom.set", {"value": 7}, "c1")
        await asyncio.sleep(0.02)
        self.assertEqual(len(self.calls), 1)
        self.device.emit("button", {"pressed": True})
        self.device.emit("button", {"pressed": False})
        await eventually(lambda: len(self.gateway.events) == 2 and not self.device.events)
        self.assertEqual([e["data"]["pressed"] for e in self.gateway.events], [True, False])
        self.assertFalse(self.device.events)

    @bounded()
    async def test_oversized_result_state_is_acknowledged_as_executed(self):
        calls = []

        async def oversized(arguments):
            calls.append(arguments)
            return {"value": "x" * 1970}

        self.device.capability("oversized.set", oversized)
        await self.start_agent()
        self.gateway.command("linux-test", "oversized.set", {}, "large-result")
        await eventually(
            lambda: self.gateway.command_status("large-result")["status"] == "executed"
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.gateway.command_status("large-result")["reported_state"], {})

    @bounded()
    async def test_revocation_is_fatal_without_retries(self):
        await self.start_agent()
        self.write_credentials(revoked=True)
        with self.assertRaises(SDKError) as error:
            await asyncio.wait_for(self.task, 1)
        self.assertEqual(error.exception.code, "revoked")
        self.assertEqual(self.agent.retries, 0)
        await eventually(lambda: not self.gateway.state("linux-test")["available"])

    @bounded()
    async def test_gateway_restart_reconnect_retains_boot_and_queued_event(self):
        await self.start_agent()
        boot = self.device.boot_id
        old_epoch = self.gateway.epoch
        port = self.server.port
        await asyncio.wait_for(self.server.close(), 5)
        self.device.emit("button", {"pressed": True})
        self.gateway = Gateway()
        self.server = await DeviceServer(self.gateway, Credentials(self.path), port=port).start()
        await eventually(lambda: self.agent.sessions >= 2)
        await eventually(lambda: len(self.gateway.events) == 1)
        self.assertNotEqual(self.gateway.epoch, old_epoch)
        self.assertEqual(self.gateway.state("linux-test")["boot_id"], boot)
        self.assertEqual(self.gateway.events[0]["event_id"], "e1")

    @bounded()
    async def test_handler_timeout_does_not_claim_success(self):
        async def slow(arguments):
            await asyncio.sleep(1)
            return {"danger": "not confirmed"}

        self.device.capability("slow", slow)
        self.agent.handler_timeout = 0.01
        await self.start_agent()
        self.gateway.command("linux-test", "slow", {}, "slow-cmd")
        await eventually(lambda: self.gateway.command_status("slow-cmd")["status"] == "failed")
        self.assertEqual(self.gateway.command_status("slow-cmd")["error"]["code"], "device_failed")
        self.assertEqual(self.device.state, {})
        # The session survives: the next command runs on the same connection.
        self.gateway.command("linux-test", "custom.set", {"value": 4}, "after-slow")
        await eventually(lambda: self.gateway.command_status("after-slow")["status"] == "executed")
        self.assertEqual((self.agent.sessions, self.agent.retries), (1, 0))
        # A replay of the timed-out ID reports the same failure without running it again.
        self.assertEqual(self.device.results["slow-cmd"][1], "handler_timeout")

    @bounded()
    async def test_late_ack_from_the_real_gateway_keeps_the_session(self):
        clock = [0.0]
        self.gateway.clock = lambda: clock[0]
        release = asyncio.Event()

        async def waits(arguments):
            await release.wait()
            return {"late": True}

        self.device.capability("waits", waits)
        self.agent.handler_timeout = 5
        await self.start_agent()
        self.gateway.command("linux-test", "waits", {}, "late-cmd")
        await eventually(lambda: self.gateway.command_status("late-cmd")["status"] == "dispatched")
        clock[0] += 60  # The gateway's ACK deadline passes while the handler runs.
        self.assertEqual(self.gateway.command_status("late-cmd")["status"], "timed_out")
        release.set()
        await eventually(lambda: self.agent.dropped_acks == 1)
        self.assertEqual(self.gateway.command_status("late-cmd")["status"], "timed_out")
        self.assertIn("late_ack", self.gateway.commands["late-cmd"])
        self.gateway.command("linux-test", "custom.set", {"value": 5}, "after-late")
        await eventually(lambda: self.gateway.command_status("after-late")["status"] == "executed")
        self.assertEqual((self.agent.sessions, self.agent.retries), (1, 0))

    @bounded()
    async def test_installed_cli_software_example(self):
        self.path.write_text(
            json.dumps({"devices": {"linux-lamp-1": {"token": TOKEN, "revoked": False}}})
        )
        self.path.chmod(0o600)
        environment = dict(os.environ, GROK_GADGETS_DEVICE_TOKEN=TOKEN)
        environment.pop("GROK_DEVICE_TOKEN", None)
        process = await asyncio.create_subprocess_exec(
            str(Path(sys.executable).parent / "grok-linux-agent"),
            "--port",
            str(self.server.port),
            "--simulate-button",
            env=environment,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            await eventually(lambda: "linux-lamp-1" in self.gateway.devices)
            args = {"r": 2, "g": 3, "b": 4, "on": True}
            self.gateway.command("linux-lamp-1", "rgb.set", args, "cli-cmd")
            await eventually(lambda: self.gateway.command_status("cli-cmd")["status"] == "executed")
            await eventually(lambda: len(self.gateway.events) == 2)
            self.assertEqual(self.gateway.state("linux-lamp-1")["state"]["rgb"], args)
            self.assertTrue(self.gateway.state("linux-lamp-1")["simulated"])
            self.assertEqual([e["data"]["pressed"] for e in self.gateway.events], [True, False])
        finally:
            if process.returncode is None:
                process.terminate()
            _, errors = await asyncio.wait_for(process.communicate(), 2)
            self.assertNotIn(TOKEN.encode(), errors)
