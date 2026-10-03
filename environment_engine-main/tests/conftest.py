"""Test setup.

The suite needs no Home Assistant install: if the real package is missing, a small stub
under tests/ha_stub takes its place. Run from the repository root with `pytest`.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import homeassistant  # noqa: F401
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent / "ha_stub"))
