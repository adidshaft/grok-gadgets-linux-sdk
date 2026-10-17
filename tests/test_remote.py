"""LIN-REMOTE-001 (hub ADR 013 §4): a Linux gadget on a relay, over TLS with a pinned CA."""

import asyncio
import ssl
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fake_gateway import FakeGateway, bounded

from grok_gadgets_linux import Agent, Device, SDKError
from grok_gadgets_linux.cli import main

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
except ImportError:  # CI installs it with the gateway extra.
    x509 = None

TOKEN = "fixture-remote-token-only"


def make_ca(name="relay test CA"):
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    return key, cert


def server_context(ca_key, ca_cert, name, folder):
    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)]))
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False
        )
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
        )
        .sign(ca_key, hashes.SHA256())
    )
    cert_file, key_file = Path(folder) / "cert.pem", Path(folder) / "key.pem"
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_file, key_file)
    return context


def pem(cert):
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def device():
    return Device("lamp-01", "test", simulated=True)


class RemoteRules(unittest.TestCase):
    def test_a_remote_gateway_needs_a_ca(self):
        with self.assertRaises(ValueError):
            Agent(device(), TOKEN, host="devices.example.net", port=8444)
        Agent(device(), TOKEN, host="127.0.0.1")  # Loopback stays as it was.


@unittest.skipIf(x509 is None, "needs cryptography (the gateway extra)")
class RemoteTls(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.ca_key, self.ca = make_ca()
        context = server_context(self.ca_key, self.ca, "localhost", self.folder.name)
        self.gateway = await FakeGateway().start(ssl=context)

    async def asyncTearDown(self):
        self.gateway.server.close()
        self.folder.cleanup()

    @bounded()
    async def test_tls_with_the_pinned_ca_and_the_name(self):
        agent = Agent(device(), TOKEN, host="localhost", port=self.gateway.port, ca=pem(self.ca))
        self.assertEqual(agent.poll_interval, 0.5)  # The relay polling interval (ADR 009).
        stop = asyncio.Event()
        task = asyncio.create_task(agent.run(stop))
        await asyncio.wait_for(agent.connected.wait(), 5)
        hello = self.gateway.received[0]
        self.assertEqual(hello["type"], "hello")
        self.assertEqual(hello["token"], TOKEN)
        stop.set()
        await task

    @bounded()
    async def test_another_ca_or_name_is_refused_and_fatal(self):
        _, other = make_ca("someone else")
        agent = Agent(
            device(),
            TOKEN,
            host="localhost",
            port=self.gateway.port,
            ca=pem(other),
            reconnect_attempts=None,
        )
        with self.assertRaises(SDKError) as refused:
            await agent.run()
        self.assertEqual(refused.exception.code, "tls_rejected")
        wrong_name = Agent(
            device(),
            TOKEN,
            host="127.0.0.1",
            port=self.gateway.port,
            ca=pem(self.ca),
            server_name="devices.example.net",
            reconnect_attempts=None,
        )
        with self.assertRaises(SDKError) as refused:
            await wrong_name.run()
        self.assertEqual(refused.exception.code, "tls_rejected")


class RemoteCli(unittest.TestCase):
    def test_gateway_needs_ca_and_token_file(self):
        import contextlib
        import io

        for argv in (
            ["--gateway", "devices.example.net"],
            ["--gateway", "devices.example.net", "--ca", "/nonexistent/ca.pem"],
            ["--gateway", "not a name:8444", "--ca", __file__],
            ["--ca", __file__],
        ):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                code = main(argv)
            self.assertEqual(code, 2, argv)

    def test_device_id_replaces_the_factory_id(self):
        import contextlib
        import io
        import os
        import socket

        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(main(["--device-id", "lamp 01"]), 2)
        self.assertIn("--device-id takes", err.getvalue())

        with socket.socket() as probe:  # A closed loopback port: the agent stops after one try.
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as folder:
            token = Path(folder) / "lamp-07.token"
            token.write_text(TOKEN)
            os.chmod(token, 0o600)
            argv = ["--device-id", "lamp-07", "--port", str(port), "--token-file", str(token)]
            with contextlib.redirect_stderr(err):
                self.assertEqual(main([*argv, "--max-attempts", "1"]), 5)
        self.assertIn("Agent starting as lamp-07; software simulation", err.getvalue())


GATEWAY_SOURCE = __import__("os").environ.get("GROK_GATEWAY_SOURCE")


@unittest.skipUnless(GATEWAY_SOURCE, "needs GROK_GATEWAY_SOURCE (CI runs it)")
@unittest.skipIf(x509 is None, "needs cryptography (the gateway extra)")
class RealRelayListener(unittest.IsolatedAsyncioTestCase):
    """The real gateway's relay listener, its own CA and device certificate."""

    @bounded()
    async def test_agent_reaches_the_relay_listener(self):
        import json
        import os
        import sys

        sys.path.insert(0, GATEWAY_SOURCE)
        from grok_gadgets_gateway import lan
        from grok_gadgets_gateway.domain import Gateway
        from grok_gadgets_gateway.transport import Credentials, DeviceServer, digest

        with tempfile.TemporaryDirectory() as folder:
            lan.create_ca(folder)
            lan.issue_device_cert("devices.example.net", folder)
            registry = Path(folder) / "credentials.json"
            registry.write_text(
                json.dumps({"devices": {"lamp-01": {"sha256": digest(TOKEN), "revoked": False}}})
            )
            os.chmod(registry, 0o600)
            gateway = Gateway()
            server = await DeviceServer(
                gateway,
                Credentials(registry),
                host="127.0.0.1",
                port=0,
                tls=lan.device_context(folder),
                public=True,
            ).start()
            try:
                agent = Agent(
                    device(),
                    TOKEN,
                    host="127.0.0.1",
                    port=server.port,
                    ca=lan.ca_pem_text(folder),
                    server_name="devices.example.net",
                    request_timeout=5.0,
                )
                stop = asyncio.Event()
                task = asyncio.create_task(agent.run(stop))
                await asyncio.wait_for(agent.connected.wait(), 5)
                self.assertIn("lamp-01", gateway.devices)
                stop.set()
                await task
            finally:
                await server.close()
