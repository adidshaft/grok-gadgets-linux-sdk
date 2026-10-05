"""Scripted loopback test peer; not a gateway implementation and never used outside tests."""

import asyncio
import functools
import json

OK_HELLO = {"ok": True, "session_id": "fake-session", "protocol_version": "0.1.0"}


def error(code):
    return {"ok": False, "error": {"code": code, "message": "scripted"}}


def bounded(seconds=20):
    """Turn a hang into a test failure instead of a stuck suite."""

    def decorate(test):
        @functools.wraps(test)
        async def wrapper(*args, **kwargs):
            await asyncio.wait_for(test(*args, **kwargs), seconds)

        return wrapper

    return decorate


class FakeGateway:
    """Answers each request with `respond(message, connection_number)`.

    The callback returns a response dict, raw bytes, or None to close the connection.
    """

    def __init__(self, respond=None):
        self.respond = respond or self.default
        self.received = []
        self.connections = 0
        self.commands = []
        self.server = None
        self.port = None

    def default(self, message, connection):
        if message["type"] == "hello":
            return OK_HELLO
        if message["type"] == "poll":
            return {"ok": True, "commands": [self.commands.pop(0)] if self.commands else []}
        return {"ok": True}

    async def start(self):
        self.server = await asyncio.start_server(self._client, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]
        return self

    async def _client(self, reader, writer):
        self.connections += 1
        number = self.connections
        try:
            while line := await reader.readline():
                message = json.loads(line)
                self.received.append(message)
                response = self.respond(message, number)
                if response is None:
                    break
                if isinstance(response, dict):
                    response = json.dumps(response, separators=(",", ":")).encode() + b"\n"
                writer.write(response)
                await writer.drain()
        except (ConnectionError, OSError):
            pass
        finally:
            writer.close()

    async def close(self):
        self.server.close()
        if hasattr(self.server, "close_clients"):
            self.server.close_clients()
        await asyncio.wait_for(self.server.wait_closed(), 2)
