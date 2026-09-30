import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

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

    def test_loopback_and_capped_backoff(self):
        with self.assertRaises(ValueError):
            Agent(self.device(), TOKEN, host="0.0.0.0")
        agent = Agent(self.device(), TOKEN, backoff_initial=0.1, backoff_cap=0.5)
        self.assertEqual([agent.retry_delay(i) for i in range(5)], [0.1, 0.2, 0.4, 0.5, 0.5])

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
        if self.task and not self.task.done():
            await asyncio.wait_for(self.task, 2)
        await self.server.close()
        self.directory.cleanup()

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

    async def test_revocation_is_fatal_without_retries(self):
        await self.start_agent()
        self.write_credentials(revoked=True)
        with self.assertRaises(SDKError) as error:
            await asyncio.wait_for(self.task, 1)
        self.assertEqual(error.exception.code, "revoked")
        self.assertEqual(self.agent.retries, 0)
        await eventually(lambda: not self.gateway.state("linux-test")["available"])

    async def test_gateway_restart_reconnect_retains_boot_and_queued_event(self):
        await self.start_agent()
        boot = self.device.boot_id
        old_epoch = self.gateway.epoch
        port = self.server.port
        await self.server.close()
        self.device.emit("button", {"pressed": True})
        self.gateway = Gateway()
        self.server = await DeviceServer(self.gateway, Credentials(self.path), port=port).start()
        await eventually(lambda: self.agent.sessions >= 2)
        await eventually(lambda: len(self.gateway.events) == 1)
        self.assertNotEqual(self.gateway.epoch, old_epoch)
        self.assertEqual(self.gateway.state("linux-test")["boot_id"], boot)
        self.assertEqual(self.gateway.events[0]["event_id"], "e1")

    async def test_handler_timeout_does_not_claim_success(self):
        async def slow(arguments):
            await asyncio.sleep(1)
            return {"danger": "not confirmed"}

        self.device.capability("slow", slow)
        self.agent.handler_timeout = 0.01
        await self.start_agent()
        self.gateway.command("linux-test", "slow", {}, "slow-cmd")
        await eventually(lambda: self.gateway.command_status("slow-cmd")["status"] == "unconfirmed")
        self.assertNotEqual(self.gateway.command_status("slow-cmd")["status"], "executed")
        self.assertEqual(self.device.state, {})

    async def test_installed_cli_software_example(self):
        self.path.write_text(
            json.dumps({"devices": {"linux-lamp-1": {"token": TOKEN, "revoked": False}}})
        )
        self.path.chmod(0o600)
        environment = dict(os.environ, GROK_DEVICE_TOKEN=TOKEN)
        process = await asyncio.create_subprocess_exec(
            "grok-linux-agent",
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
