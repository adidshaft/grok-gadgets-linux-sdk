"""Linux wheel acceptance inside pinned Python container, with networking disabled."""

import importlib.metadata
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

sdk = Path("/sdk")
wheel = sdk / "dist/grok_gadgets_linux_sdk-0.1.0a1-py3-none-any.whl"
subprocess.run(
    [sys.executable, "-m", "pip", "install", "--no-index", "--find-links=/wheels", str(wheel)],
    check=True,
)
import grok_gadgets_linux  # noqa: E402

print(
    json.dumps(
        {
            "platform": platform.platform(),
            "kernel": platform.release(),
            "python": platform.python_version(),
            "machine": platform.machine(),
            "installed_package": grok_gadgets_linux.__file__,
            "versions": {
                name: importlib.metadata.version(name)
                for name in ["grok-gadgets-linux-sdk", "jsonschema", "rpds-py"]
            },
        },
        indent=2,
    ),
    flush=True,
)
environment = dict(os.environ, GROK_GATEWAY_SOURCE="/gateway/src")
subprocess.run(
    [sys.executable, "-m", "unittest", "discover", "-s", str(sdk / "tests"), "-v"],
    env=environment,
    cwd=sdk,
    check=True,
)
subprocess.run(["grok-linux-agent", "--help"], check=True)
