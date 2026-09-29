"""Vendored, hash-pinned gateway contracts; no independently authored schemas."""

import hashlib
import json
from importlib.resources import files

from jsonschema import Draft202012Validator

VERSION = "0.1.0"
MAX_FRAME = 2048
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


class SDKError(Exception):
    """Fixed safe SDK error code; do not expose untrusted device/transport text."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def validate_request(message):
    if not REQUEST_VALIDATOR.is_valid(message):
        raise SDKError("invalid_request")
    encoded = json.dumps(message, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    if len(encoded) > MAX_FRAME:
        raise SDKError("frame_too_large")
    return encoded


def validate_state(state):
    if not STATE_VALIDATOR.is_valid(state):
        raise SDKError("invalid_state")
    # Finite JSON values only, and verify standalone state fits a transport frame.
    validate_request({"type": "state", "state": state})


def validate_inline_schema(schema):
    def refs(value):
        if isinstance(value, dict):
            return any(key in {"$ref", "$dynamicRef"} or refs(item) for key, item in value.items())
        return isinstance(value, list) and any(refs(item) for item in value)

    if refs(schema):
        raise SDKError("schema_reference_forbidden")
    try:
        Draft202012Validator.check_schema(schema)
    except Exception:
        raise SDKError("invalid_schema") from None
