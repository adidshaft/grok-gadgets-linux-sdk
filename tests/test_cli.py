import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from grok_gadgets_linux.cli import FactoryError, load_factory, main


class FactoryTests(unittest.TestCase):
    def test_builtin_and_explicit_file_without_path_mutation(self):
        self.assertTrue(load_factory("grok_gadgets_linux.examples:software_lamp").simulated)
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "gadget.py"
            file.write_text(
                'from grok_gadgets_linux import Device\ndef create():\n return Device("test", "test", simulated=True)\n'
            )
            before = list(sys.path)
            self.assertEqual(load_factory(f"{file}:create", file=True).device_id, "test")
            self.assertEqual(sys.path, before)

    def test_annotated_dataclasses_repeated_loads_and_same_filename(self):
        source = """from __future__ import annotations
from dataclasses import dataclass
from grok_gadgets_linux import Device

@dataclass
class Settings:
    label: str = "LABEL"

def create():
    return Device("test", Settings().label, simulated=True, state={"module": __name__})
"""
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first" / "gadget.py"
            second = Path(directory) / "second" / "gadget.py"
            first.parent.mkdir()
            second.parent.mkdir()
            first.write_text(source.replace("LABEL", "first"))
            second.write_text(source.replace("LABEL", "second"))
            before = list(sys.path)
            devices = [load_factory(f"{path}:create", file=True) for path in (first, first, second)]
            names = [device.state["module"] for device in devices]
            self.assertEqual(len(set(names)), 3)
            self.assertEqual(
                [sys.modules[name].Settings().label for name in names], ["first", "first", "second"]
            )
            self.assertEqual(sys.path, before)
            # Existing class metadata still resolves its defining module after subsequent loads.
            from typing import get_type_hints

            for name in names:
                self.assertEqual(get_type_hints(sys.modules[name].Settings), {"label": str})

    def test_failed_file_load_rolls_back_its_module_registration(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "failed.py"
            file.write_text('raise RuntimeError("PRIVATE_TOKEN")\n')
            before = {name for name in sys.modules if name.startswith("_grok_trusted_factory_")}
            with self.assertRaises(FactoryError) as caught:
                load_factory(f"{file}:create", file=True)
            after = {name for name in sys.modules if name.startswith("_grok_trusted_factory_")}
            self.assertEqual(after, before)
            self.assertNotIn("PRIVATE_TOKEN", str(caught.exception))

    def test_safe_actionable_failure_categories(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "gadget.py"
            cases = [
                ('raise RuntimeError("PRIVATE_TOKEN")', "could not load"),
                ('def create():\n raise RuntimeError("PRIVATE_TOKEN")', "function failed"),
                ("create = 7", "function unavailable"),
                ("def create():\n return 7", "must return"),
                ("syntax ??? PRIVATE_TOKEN", "could not load"),
            ]
            for source, category in cases:
                file.write_text(source)
                with self.assertRaises(FactoryError) as caught:
                    load_factory(f"{file}:create", file=True)
                self.assertIn(category, str(caught.exception))
                self.assertNotIn("PRIVATE_TOKEN", str(caught.exception))
            for factory, is_file, category in [
                ("broken", False, "Use module:function"),
                ("absent_private_module:create", False, "module could not load"),
                (f"{file}:absent", True, "function unavailable"),
                (f"{file}.missing:create", True, "file unavailable"),
                ("x:create()", False, "Use module:function"),
            ]:
                # Replace stale invalid source so the missing function reaches lookup.
                file.write_text("value = 1\n")
                with self.assertRaises(FactoryError) as caught:
                    load_factory(factory, file=is_file)
                self.assertIn(category, str(caught.exception))

    def test_cli_reports_category_without_private_input(self):
        errors = io.StringIO()
        with patch.object(sys, "argv", ["grok-linux-agent", "--factory", "PRIVATE_TOKEN:create"]):
            with contextlib.redirect_stderr(errors):
                self.assertEqual(main(), 1)
        self.assertIn("install it or use --factory-file", errors.getvalue())
        self.assertNotIn("PRIVATE_TOKEN", errors.getvalue())
