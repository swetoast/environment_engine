"""Entity-list normalization used by every multi-entity slot reader."""
from custom_components.environment_engine.entities import as_list


def test_none_and_empty_become_empty_list():
    assert as_list(None) == []
    assert as_list("") == []
    assert as_list([]) == []


def test_single_string_is_wrapped():
    assert as_list("fan.one") == ["fan.one"]


def test_list_is_passed_through_dropping_blanks():
    assert as_list(["fan.one", "fan.two"]) == ["fan.one", "fan.two"]
    assert as_list(["fan.one", "", None]) == ["fan.one"]
