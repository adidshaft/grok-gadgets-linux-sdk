"""Reusable capability handlers, state, queued events, and bounded boot-local dedup."""

import asyncio
import contextvars
import copy
import inspect
import json
import uuid
from collections import OrderedDict, deque
from functools import partial

from jsonschema import Draft202012Validator

from .contracts import (
    ACK_ERRORS,
    EVENT_KIND,
    RESERVED_EVENTS,
    RGB_SCHEMA,
    VERSION,
    SCHEMA,
    SDKError,
    validate_inline_schema,
    validate_request,
    worst_case_ack,
)
from .contracts import validate_state


def _is_async(function):
    return inspect.iscoroutinefunction(function) or inspect.iscoroutinefunction(
        getattr(function, "__call__", None)
    )


class Device:
    def __init__(
        self,
        device_id,
        model,
        *,
        firmware_version="0.1.0a1",
        simulated=False,
        boot_id=None,
        state=None,
        event_limit=64,
        command_limit=128,
    ):
        if type(event_limit) is not int or not 1 <= event_limit <= 128:
            raise ValueError("event_limit must be 1..128")
        if type(command_limit) is not int or not 1 <= command_limit <= 128:
            raise ValueError("command_limit must be 1..128")
        self.device_id = device_id
        self.model = model
        self.firmware_version = firmware_version
        self.simulated = simulated
        self.boot_id = boot_id or uuid.uuid4().hex
        self._state = copy.deepcopy(state if state is not None else {})
        validate_state(self._state)
        self.handlers = {}
        self.schemas = {}
        self.event_names = set()
        self.events = deque()
        self.event_limit = event_limit
        self.command_limit = command_limit
        self.results = OrderedDict()
        self._event_sequence = 0
        self._execution_lock = asyncio.Lock()
        self._shutdown_callbacks = []
        self._thread = None

    @property
    def state(self):
        return copy.deepcopy(self._state)

    def publish_state(self, state):
        validate_state(state)
        self._state = copy.deepcopy(state)

    def _check_name(self, name):
        if name == "state" or not Draft202012Validator(SCHEMA["$defs"]["id"]).is_valid(name):
            raise SDKError("invalid_capability")
        if name in self.handlers or name in self.event_names:
            raise SDKError("duplicate_capability")

    def capability(self, name, handler, *, schema=None):
        """Register a handler returning a full observed-state object.

        Async handlers run on the event loop. Plain functions run in a worker thread, so
        blocking GPIO/I2C/SPI calls do not stall polling; the handler timeout bounds the
        wait, but a timed-out thread keeps running until the function returns.
        """
        self._check_name(name)
        if name in RESERVED_EVENTS:
            raise SDKError("invalid_capability")
        if not callable(handler):
            raise TypeError("Capability handlers must be callable")
        if name == "rgb.set":
            schema = RGB_SCHEMA
        if schema is not None:
            validate_inline_schema(schema)
            self.schemas[name] = copy.deepcopy(schema)
        self.handlers[name] = handler
        return self

    def event_capability(self, name):
        """Declare an input event; custom names are marked so gateways never offer a command."""
        self._check_name(name)
        if name == "history_lost":
            raise SDKError("invalid_capability")
        self.event_names.add(name)
        return self

    def on_shutdown(self, callback):
        """Register a callback run when the agent stops, after in-flight handlers are cancelled.

        Use it to put actuators in a safe state. Callbacks run in reverse registration order;
        each is bounded by the agent handler timeout and its exceptions are suppressed.
        """
        if not callable(callback):
            raise TypeError("Shutdown callbacks must be callable")
        self._shutdown_callbacks.append(callback)
        return callback

    async def _call(self, function, *args):
        if _is_async(function):
            return await function(*args)
        if self._thread is not None and not self._thread.done():
            # A timed-out thread is still running: never run two blocking calls at once.
            await asyncio.wait({self._thread})
        loop = asyncio.get_running_loop()
        context = contextvars.copy_context()
        self._thread = loop.run_in_executor(None, partial(context.run, function, *args))
        return await asyncio.shield(self._thread)

    async def shutdown(self, timeout=5.0):
        for callback in reversed(self._shutdown_callbacks):
            try:
                await asyncio.wait_for(self._call(callback), timeout)
            except Exception:
                pass  # Fixed behavior: shutdown continues; callback text is never reported.

    def hello(self, token):
        device = {
            "device_id": self.device_id,
            "model": self.model,
            "firmware_version": self.firmware_version,
            "boot_id": self.boot_id,
            "simulated": self.simulated,
            "capabilities": sorted([*self.handlers, *self.event_names, "state"]),
            "state": self.state,
        }
        schemas = {name: schema for name, schema in self.schemas.items() if name != "rgb.set"}
        for name in sorted(self.event_names - RESERVED_EVENTS):
            schemas[name] = {"type": "object", EVENT_KIND: "event"}
        if schemas:
            device["capability_schemas"] = schemas
        message = {"type": "hello", "protocol_version": VERSION, "token": token, "device": device}
        validate_request(message)
        return message

    def emit(self, name, data, *, observed_at=None):
        if name not in self.event_names:
            raise SDKError("unsupported_event")
        if len(self.events) >= self.event_limit:
            raise SDKError("event_queue_full")
        if not isinstance(data, dict):
            raise SDKError("invalid_event")
        if name == "button" and (set(data) != {"pressed"} or type(data["pressed"]) is not bool):
            raise SDKError("invalid_button_event")
        next_sequence = self._event_sequence + 1
        event = {
            "type": "event",
            "event_id": f"e{next_sequence}",
            "name": name,
            "data": copy.deepcopy(data),
        }
        if observed_at is not None:
            event["observed_at"] = observed_at
        validate_request(event)
        self.events.append(event)
        self._event_sequence = next_sequence
        return event["event_id"]

    async def execute(self, command):
        async with self._execution_lock:
            return await self._execute(command)

    def _ack(self, cid, error=None):
        ack = {
            "type": "ack",
            "command_id": cid,
            "status": "failed" if error else "executed",
            "state": self.state,
        }
        if error:
            ack["error"] = {"code": error, "message": ACK_ERRORS[error]}
        validate_request(ack)
        return ack

    @staticmethod
    def _fingerprint(command):
        return json.dumps(
            {"capability": command["capability"], "arguments": command["arguments"]},
            sort_keys=True,
            allow_nan=False,
        )

    def _remember(self, cid, fingerprint, error):
        self.results[cid] = (fingerprint, error)
        while len(self.results) > self.command_limit:
            self.results.popitem(last=False)

    def timed_out(self, command):
        """Failed ACK for a handler that overran; a replay of this ID reports the same."""
        cid = command["command_id"]
        self._remember(cid, self._fingerprint(command), "handler_timeout")
        return self._ack(cid, "handler_timeout")

    async def _execute(self, command):
        cid = command["command_id"]
        # Validate identifiers and the largest possible ACK before any physical handler runs.
        validate_request(worst_case_ack(self.state, cid))
        fingerprint = self._fingerprint(command)
        if cid in self.results:
            previous, error = self.results[cid]
            if previous != fingerprint:
                # The gateway forgot this ID (restart/eviction); refuse without executing.
                return self._ack(cid, "duplicate_conflict")
            # Replay: original outcome, current observed state.
            return self._ack(cid, error)
        capability = command["capability"]
        arguments = command["arguments"]
        error = None
        if capability not in self.handlers:
            error = "unsupported_capability"
        elif not isinstance(arguments, dict):
            error = "invalid_arguments"
        elif capability in self.schemas and not Draft202012Validator(
            self.schemas[capability]
        ).is_valid(arguments):
            error = "invalid_arguments"
        if error is None:
            try:
                reported = await self._call(self.handlers[capability], copy.deepcopy(arguments))
                self.publish_state(reported)
            except SDKError as exc:
                if exc.code == "frame_too_large":
                    # The side effect already completed. Keep the last-known-good state
                    # and report execution; marking this failed would invite a retry.
                    pass
                else:
                    error = "handler_failed"
            except Exception:
                # Handler errors may include credentials: return only a fixed failure.
                error = "handler_failed"
        ack = self._ack(cid, error)
        self._remember(cid, fingerprint, error)
        return ack
