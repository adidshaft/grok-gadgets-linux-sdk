"""Single-session loopback device agent; no internet or model calls."""

import asyncio
import json
import time

from .contracts import MAX_FRAME, RESPONSE_VALIDATOR, VERSION, SDKError, validate_request

_FATAL = {"unauthorized", "revoked", "protocol_mismatch", "invalid_request", "duplicate_conflict"}
_KNOWN_ERRORS = _FATAL | {"stale_session", "unknown_command", "busy", "unavailable"}


class Agent:
    def __init__(
        self,
        device,
        token,
        *,
        host="127.0.0.1",
        port=8765,
        poll_interval=0.1,
        reconnect_attempts=8,
        backoff_initial=0.25,
        backoff_cap=5.0,
        request_timeout=2.0,
        handler_timeout=5.0,
    ):
        if host not in {"127.0.0.1", "::1"}:
            raise ValueError("Alpha transport supports loopback IPs only")
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("Invalid port")
        if not 0.01 <= poll_interval <= 0.5:
            raise ValueError("Poll interval must be 0.01..0.5 seconds")
        if type(reconnect_attempts) is not int or not 1 <= reconnect_attempts <= 32:
            raise ValueError("Reconnect attempts must be 1..32")
        if not 0 < backoff_initial <= backoff_cap <= 60:
            raise ValueError("Backoff must be positive and capped at 60 seconds")
        if not 0 < request_timeout <= 10 or not 0 < handler_timeout <= 10:
            raise ValueError("Timeouts must be positive and at most 10 seconds")
        device.hello(token)  # Validate descriptor, credential shape and frame before connecting.
        self.device, self.token = device, token
        self.host, self.port = host, port
        self.poll_interval = poll_interval
        self.reconnect_attempts = reconnect_attempts
        self.backoff_initial, self.backoff_cap = backoff_initial, backoff_cap
        self.request_timeout, self.handler_timeout = request_timeout, handler_timeout
        self.connected = asyncio.Event()
        self.sessions = 0
        self.retries = 0

    def retry_delay(self, attempt):
        return min(self.backoff_cap, self.backoff_initial * (2 ** min(attempt, 16)))

    async def exchange(self, reader, writer, message):
        writer.write(validate_request(message))
        await asyncio.wait_for(writer.drain(), self.request_timeout)
        line = await asyncio.wait_for(reader.readline(), self.request_timeout)
        if not line or not line.endswith(b"\n") or len(line) > MAX_FRAME:
            raise SDKError("connection_lost")
        try:
            response = json.loads(line)
        except (ValueError, UnicodeError):
            raise SDKError("invalid_response") from None
        if not RESPONSE_VALIDATOR.is_valid(response):
            raise SDKError("invalid_response")
        if not response["ok"]:
            code = response["error"]["code"]
            raise SDKError(code if code in _KNOWN_ERRORS else "remote_error")
        return response

    async def _session(self, stop):
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port, limit=MAX_FRAME), self.request_timeout
        )
        try:
            hello = await self.exchange(reader, writer, self.device.hello(self.token))
            if hello.get("protocol_version") != VERSION or not hello.get("session_id"):
                raise SDKError("protocol_mismatch")
            self.sessions += 1
            self.connected.set()
            while not stop.is_set():
                if self.device.events:
                    event = self.device.events[0]
                    await self.exchange(reader, writer, event)
                    self.device.events.popleft()  # Lost response retains same event ID for retry.
                await self.exchange(reader, writer, {"type": "state", "state": self.device.state})
                response = await self.exchange(reader, writer, {"type": "poll"})
                commands = response.get("commands")
                if not isinstance(commands, list) or len(commands) > 1:
                    raise SDKError("invalid_response")
                for command in commands:
                    # A cancelled/timed-out handler receives no success ACK; gateway stays unconfirmed.
                    ack = await asyncio.wait_for(self.device.execute(command), self.handler_timeout)
                    await self.exchange(reader, writer, ack)
                try:
                    await asyncio.wait_for(stop.wait(), self.poll_interval)
                except TimeoutError:
                    pass
        finally:
            self.connected.clear()
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass

    async def run(self, stop=None):
        stop = stop or asyncio.Event()
        failures = 0
        while not stop.is_set():
            started = time.monotonic()
            try:
                await self._session(stop)
                return
            except SDKError as error:
                if error.code in _FATAL or error.code in {"invalid_response", "frame_too_large"}:
                    raise
            except (OSError, TimeoutError, ValueError):
                pass
            if stop.is_set():
                return
            if time.monotonic() - started >= 10:
                failures = 0
            failures += 1
            self.retries += 1
            if failures >= self.reconnect_attempts:
                raise SDKError("reconnect_exhausted")
            try:
                await asyncio.wait_for(stop.wait(), self.retry_delay(failures - 1))
            except TimeoutError:
                pass
