"""The package itself: what Home Assistant and HACS need before any logic runs.

A broken manifest, a module that does not import, an option without a label or without a
default: each of these stops the integration loading or leaves a blank field in the UI.
"""
import dataclasses
import importlib
import json
import pkgutil
import re
from pathlib import Path

import pytest

import custom_components.environment_engine as package
from custom_components.environment_engine import const
from custom_components.environment_engine.options import EngineOptions, resolved_options

COMPONENT = Path(package.__file__).parent
ROOT = COMPONENT.parent.parent


def test_manifest_hacs_and_repository_layout():
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    for key in ("domain", "name", "version", "documentation", "issue_tracker", "codeowners", "config_flow"):
        assert manifest.get(key), f"manifest.json is missing {key}"
    assert manifest["domain"] == const.DOMAIN == COMPONENT.name
    assert re.fullmatch(r"\d+\.\d+\.\d+", manifest["version"])
    assert json.loads((ROOT / "hacs.json").read_text())["name"]
    assert (ROOT / "README.md").read_text().strip() and (ROOT / "LICENSE").exists()
    # Tests live in /tests, never inside the component that gets installed.
    assert not (COMPONENT / "tests").exists()
    assert not [p.name for p in COMPONENT.rglob("*.md")]


def test_every_module_imports():
    for module in pkgutil.walk_packages([str(COMPONENT)], prefix=package.__name__ + "."):
        if module.name.endswith("config_flow"):
            pytest.importorskip("voluptuous")
        importlib.import_module(module.name)


def test_options_have_defaults_bounds_and_labels():
    fields = {field.name for field in dataclasses.fields(EngineOptions)}
    # Garbage in every option still resolves to a usable, bounded configuration.
    garbage = resolved_options({}, {key: "not a number" for key in const.DEFAULTS})
    clean = resolved_options({}, {})
    assert garbage == clean
    assert {field for field in fields if getattr(clean, field) is None} == set()
    extreme = resolved_options({}, {key: 10 ** 9 for key in const.DEFAULTS})
    assert 16 <= extreme.target_temperature <= 30 and extreme.lightning_distance <= 40
    assert resolved_options({}, {key: -(10 ** 9) for key in const.DEFAULTS}).update_interval >= 15

    strings = json.loads((COMPONENT / "strings.json").read_text())
    assert strings == json.loads((COMPONENT / "translations" / "en.json").read_text())
    text = json.dumps(strings)
    missing = [key for key in list(const.DEFAULTS) + list(const.ENTITY_KEYS) if f'"{key}"' not in text]
    assert missing == [], f"no label in strings.json for: {missing}"
