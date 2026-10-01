"""_resolve_strategy and resolve_locator: dispatch by kind, nth selection, fallback chains, frame descent, and error paths."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from capability_agent.artifact.schema import Locator, LocatorKind, LocatorStrategy
from capability_agent.surface.browser import LocatorResolutionError, _resolve_strategy, resolve_locator


def _fake_candidate():
    candidate = MagicMock()
    candidate.wait_for.return_value = None
    return candidate


def test_resolve_strategy_dispatches_by_kind():
    scope = MagicMock()
    scope.get_by_role.return_value = _fake_candidate()
    _resolve_strategy(scope, LocatorStrategy(kind=LocatorKind.ROLE, value="Search", role="button"))
    scope.get_by_role.assert_called_once_with("button", name="Search")

    scope = MagicMock()
    scope.get_by_text.return_value = _fake_candidate()
    _resolve_strategy(scope, LocatorStrategy(kind=LocatorKind.TEXT, value="Hello"))
    scope.get_by_text.assert_called_once_with("Hello", exact=False)

    scope = MagicMock()
    scope.locator.return_value = _fake_candidate()
    _resolve_strategy(scope, LocatorStrategy(kind=LocatorKind.CSS, value="#id"))
    scope.locator.assert_called_once_with("#id")


def test_resolve_strategy_dispatches_label_test_id_and_xpath():
    scope = MagicMock()
    scope.get_by_label.return_value = _fake_candidate()
    _resolve_strategy(scope, LocatorStrategy(kind=LocatorKind.LABEL, value="Nickname"))
    scope.get_by_label.assert_called_once_with("Nickname")

    scope.get_by_test_id.return_value = _fake_candidate()
    _resolve_strategy(scope, LocatorStrategy(kind=LocatorKind.TEST_ID, value="submit-btn"))
    scope.get_by_test_id.assert_called_once_with("submit-btn")

    scope.locator.return_value = _fake_candidate()
    _resolve_strategy(scope, LocatorStrategy(kind=LocatorKind.XPATH, value="//button"))
    scope.locator.assert_called_once_with("xpath=//button")


def test_resolve_strategy_applies_nth():
    scope = MagicMock()
    candidate = _fake_candidate()
    scope.get_by_role.return_value = candidate
    _resolve_strategy(scope, LocatorStrategy(kind=LocatorKind.ROLE, value="", role="textbox", nth=2))
    candidate.nth.assert_called_once_with(2)


def test_resolve_strategy_raises_on_unknown_kind():
    scope = MagicMock()
    fake_strategy = SimpleNamespace(kind="not-a-real-kind", value="x", nth=None)
    with pytest.raises(ValueError, match="Unknown locator kind"):
        _resolve_strategy(scope, fake_strategy)


def test_resolve_locator_falls_back_when_primary_fails():
    page = MagicMock()
    failing = MagicMock()
    failing.wait_for.side_effect = Exception("not found")
    working = _fake_candidate()
    page.get_by_role.return_value = failing
    page.get_by_text.return_value = working
    locator = Locator(
        primary=LocatorStrategy(kind=LocatorKind.ROLE, value="Go", role="button"),
        fallbacks=[LocatorStrategy(kind=LocatorKind.TEXT, value="Go")],
    )
    result = resolve_locator(page, locator)
    assert result is working


def test_resolve_locator_raises_when_every_strategy_fails():
    page = MagicMock()
    failing = MagicMock()
    failing.wait_for.side_effect = Exception("nope")
    page.get_by_role.return_value = failing
    locator = Locator(primary=LocatorStrategy(kind=LocatorKind.ROLE, value="Go", role="button"))
    with pytest.raises(LocatorResolutionError):
        resolve_locator(page, locator)


def test_resolve_locator_descends_frame_path_before_resolving():
    page = MagicMock()
    frame_scope = MagicMock()
    frame_scope.get_by_role.return_value = _fake_candidate()
    page.frame_locator.return_value = frame_scope
    locator = Locator(
        primary=LocatorStrategy(kind=LocatorKind.ROLE, value="Go", role="button"),
        frame_path=["#inner-frame"],
    )
    resolve_locator(page, locator)
    page.frame_locator.assert_called_once_with("#inner-frame")
    frame_scope.get_by_role.assert_called_once()
