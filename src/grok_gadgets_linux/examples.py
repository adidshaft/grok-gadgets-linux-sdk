"""Software simulation only. Replace handlers with your authorized peripheral code."""

from .device import Device


def software_lamp():
    device = Device(
        "linux-lamp-1",
        "Linux software lamp",
        simulated=True,
        state={"rgb": {"r": 0, "g": 0, "b": 0, "on": False}, "button": {"pressed": False}},
    )

    async def set_rgb(arguments):
        state = device.state
        state["rgb"] = arguments
        return state

    device.capability("rgb.set", set_rgb).event_capability("button")
    return device
