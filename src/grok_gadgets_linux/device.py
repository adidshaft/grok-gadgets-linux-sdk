"""Reusable capability handlers, state, queued events, and bounded boot-local dedup."""

import asyncio
import copy
import inspect
import json
import uuid
from collections import OrderedDict, deque

from jsonschema import Draft202012Validator

from .contracts import (
    RGB_SCHEMA,
    VERSION,
    SCHEMA,
    SDKError,
    validate_inline_schema,
    validate_request,
)
from .contracts import validate_state


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

    @property
    def state(self):
        return copy.deepcopy(self._state)

    def publish_state(self, state):
        validate_state(state)
        self._state = copy.deepcopy(state)

    def capability(self, name, handler, *, schema=None):
        """Register an async handler returning a full observed-state object."""
        if name == "state" or not Draft202012Validator(SCHEMA["$defs"]["id"]).is_valid(name):
            raise SDKError("invalid_capability")
        if name in self.handlers or name in self.event_names:
            raise SDKError("duplicate_capability")
        if not inspect.iscoroutinefunction(handler):
            raise TypeError("Capability handlers must be async functions")
        if name == "rgb.set":
            schema = RGB_SCHEMA
        if schema is not None:
            validate_inline_schema(schema)
            self.schemas[name] = copy.deepcopy(schema)
        self.handlers[name] = handler
        return self

    def event_capability(self, name):
        if name == "state" or not Draft202012Validator(SCHEMA["$defs"]["id"]).is_valid(name):
            raise SDKError("invalid_capability")
        if name in self.handlers or name in self.event_names:
            raise SDKError("duplicate_capability")
        self.event_names.add(name)
        return self

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

    async def _execute(self, command):
        cid = command["command_id"]
        # Validate identifiers/frame before any potentially physical handler executes.
        validate_request(
            {"type": "ack", "command_id": cid, "status": "executed", "state": self.state}
        )
        fingerprint = json.dumps(
            {"capability": command["capability"], "arguments": command["arguments"]},
            sort_keys=True,
            allow_nan=False,
        )
        if cid in self.results:
            previous, ack = self.results[cid]
            if previous != fingerprint:
                raise SDKError("duplicate_conflict")
            return copy.deepcopy(ack)
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
                reported = await self.handlers[capability](copy.deepcopy(arguments))
                self.publish_state(reported)
            except Exception:
                # Handler errors may include credentials: return only a fixed failure.
                error = "handler_failed"
        ack = {
            "type": "ack",
            "command_id": cid,
            "status": "failed" if error else "executed",
            "state": self.state,
        }
        if error:
            ack["error"] = {
                "code": error,
                "message": "Device could not confirm requested execution",
            }
        validate_request(ack)
        self.results[cid] = (fingerprint, copy.deepcopy(ack))
        while len(self.results) > self.command_limit:
            self.results.popitem(last=False)
        return ack
