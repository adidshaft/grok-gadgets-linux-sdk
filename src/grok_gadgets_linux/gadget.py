"""Decorator API: describe each command once; the schema comes from its type hints."""

import inspect
import types
import typing
from dataclasses import dataclass

from .contracts import SDKError
from .device import Device

_SIMPLE = {bool: "boolean", int: "integer", float: "number", str: "string"}


@dataclass(frozen=True)
class Range:
    """Bounds for a number parameter: Annotated[int, Range(0, 100)]."""

    minimum: float | None = None
    maximum: float | None = None


def _schema_for(annotation):
    """JSON Schema for one parameter annotation; raise TypeError for unsupported types."""
    if annotation in _SIMPLE:
        return {"type": _SIMPLE[annotation]}
    origin = typing.get_origin(annotation)
    arguments = typing.get_args(annotation)
    if origin is typing.Annotated:
        schema = _schema_for(arguments[0])
        for extra in arguments[1:]:
            if isinstance(extra, str):
                schema["description"] = extra
            elif isinstance(extra, Range):
                if extra.minimum is not None:
                    schema["minimum"] = extra.minimum
                if extra.maximum is not None:
                    schema["maximum"] = extra.maximum
        return schema
    if origin is typing.Literal:
        if not all(type(value) in _SIMPLE for value in arguments):
            raise TypeError("Literal values must be bool, int, float or str")
        return {"enum": list(arguments)}
    if origin is list and len(arguments) == 1:
        return {"type": "array", "items": _schema_for(arguments[0])}
    if origin in (typing.Union, types.UnionType):
        options = [value for value in arguments if value is not type(None)]
        if len(options) == 1:
            return _schema_for(options[0])
    raise TypeError(f"Unsupported parameter type {annotation!r}")


def schema_from_signature(function):
    """An object schema with one property per parameter; defaults make it optional."""
    properties, required = {}, []
    hints = typing.get_type_hints(function, include_extras=True)
    for name, parameter in inspect.signature(function).parameters.items():
        if parameter.kind not in (parameter.POSITIONAL_OR_KEYWORD, parameter.KEYWORD_ONLY):
            raise TypeError("Use named parameters only (no *args or **kwargs)")
        if name not in hints:
            raise TypeError(f"Parameter {name!r} needs a type hint, for example {name}: bool")
        properties[name] = _schema_for(hints[name])
        if parameter.default is parameter.empty:
            required.append(name)
    schema = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        schema["required"] = required
    return schema


class Gadget(Device):
    """A simulated-by-default device with decorator-registered commands.

        lamp = Gadget("desk-lamp", "Desk lamp")

        @lamp.command("Turn the desk lamp on or off")
        def set_light(on: bool) -> dict:
            return {"on": on}

    The command is named after the function with underscores as dots (`set.light`). Its
    arguments arrive as keyword arguments. The returned dict updates the reported state;
    return None to leave it unchanged. Plain functions run in a worker thread; async
    functions run on the event loop.
    """

    def __init__(self, device_id, name, *, simulated=True, state=None, **options):
        super().__init__(device_id, name, simulated=simulated, state=state, **options)

    def command(self, description, *, name=None):
        if not isinstance(description, str):
            raise TypeError("Describe the command first: @gadget.command('What it does')")

        def register(function):
            capability = name or function.__name__.replace("_", ".")
            schema = schema_from_signature(function)
            if inspect.iscoroutinefunction(function):

                async def handler(arguments):
                    return self._merge(await function(**arguments))

            else:

                def handler(arguments):
                    return self._merge(function(**arguments))

            self.capability(capability, handler, schema=schema, description=description)
            return function

        return register

    def event(self, name, description=None):
        """Declare an event your code sends with gadget.emit(name, data)."""
        self.event_capability(name, description=description)
        return self

    def _merge(self, update):
        if update is None:
            return self.state
        if not isinstance(update, dict):
            raise SDKError("invalid_state")
        return {**self.state, **update}
