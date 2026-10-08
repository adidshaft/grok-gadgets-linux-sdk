"""Vendored, hash-pinned gateway contracts; no independently authored schemas."""

import hashlib
import json
from importlib.resources import files

from jsonschema import Draft202012Validator

VERSION = "0.1.0"
# Every frame fits 2048 bytes, except a TCP hello, which may use 16 KiB so that it can
# carry schemas and descriptions for every capability (protocol 0.1.0 README, Transport).
MAX_FRAME = 2048
MAX_HELLO_FRAME = 16384
_root = files("grok_gadgets_linux").joinpath("protocol")
SOURCE = json.loads(_root.joinpath("source.json").read_text())
for _name, _digest in SOURCE["files"].items():
    if hashlib.sha256(_root.joinpath(VERSION, _name).read_bytes()).hexdigest() != _digest:
        raise RuntimeError("Pinned protocol artifact hash mismatch")
SCHEMA = json.loads(_root.joinpath(VERSION, "device-request.schema.json").read_text())
RESPONSE_SCHEMA = json.loads(_root.joinpath(VERSION, "device-response.schema.json").read_text())
REQUEST_VALIDATOR = Draft202012Validator(SCHEMA)
RESPONSE_VALIDATOR = Draft202012Validator(RESPONSE_SCHEMA)
_state = dict(SCHEMA)
_state.pop("oneOf")
_state["$ref"] = "#/$defs/state"
STATE_VALIDATOR = Draft202012Validator(_state)
RGB_SCHEMA = SCHEMA["$defs"]["rgb"]
# Fixed device-side failure messages; never include handler, argument or transport text.
ACK_ERRORS = {
    "unsupported_capability": "Device could not confirm requested execution",
    "invalid_arguments": "Device could not confirm requested execution",
    "handler_failed": "Device could not confirm requested execution",
    "handler_timeout": "Handler did not finish in time; check state before acting again",
    "duplicate_conflict": "Command ID reused with changed arguments; not executed",
}
EVENT_KIND = "x-grok-gadgets-kind"
RESERVED_EVENTS = {"button", "history_lost"}


class SDKError(Exception):
    """Fixed safe SDK error code; do not expose untrusted device/transport text."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def validate_request(message, limit=MAX_FRAME):
    if not REQUEST_VALIDATOR.is_valid(message):
        raise SDKError("invalid_request")
    try:
        encoded = json.dumps(message, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    except (ValueError, TypeError, RecursionError):
        raise SDKError("invalid_request") from None
    if len(encoded) > limit:
        raise SDKError("frame_too_large")
    return encoded


def worst_case_ack(state, command_id="x" * 64):
    code, message = max(ACK_ERRORS.items(), key=lambda item: len(item[0]) + len(item[1]))
    return {
        "type": "ack",
        "command_id": command_id,
        "status": "failed",
        "state": state,
        "error": {"code": code, "message": message},
    }


def validate_state(state):
    if not STATE_VALIDATOR.is_valid(state):
        raise SDKError("invalid_state")
    # Finite JSON values only; the largest failed ACK carrying this state must fit a frame.
    validate_request(worst_case_ack(state))


def validate_inline_schema(schema):
    def refs(value):
        if isinstance(value, dict):
            return any(key in {"$ref", "$dynamicRef"} or refs(item) for key, item in value.items())
        return isinstance(value, list) and any(refs(item) for item in value)

    if refs(schema):
        raise SDKError("schema_reference_forbidden")
    try:
        Draft202012Validator.check_schema(schema)
    except Exception:  # noqa: BLE001 - any schema problem is reported as invalid_schema
        raise SDKError("invalid_schema") from None
