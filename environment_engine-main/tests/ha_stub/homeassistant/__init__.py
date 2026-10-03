"""A minimal stand-in for Home Assistant, so the suite runs with nothing installed.

Only what the integration imports at module level. It is used solely when the real
`homeassistant` package is not importable (see tests/conftest.py).
"""
