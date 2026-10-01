"""Playwright-backed browser session with robust, fallback-based locating."""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Frame, Page, sync_playwright

from capability_agent.artifact.schema import Locator, LocatorKind, LocatorStrategy


class LocatorResolutionError(Exception):
    """None of a locator's strategies (primary or fallback) found an element."""


def _resolve_strategy(scope: Page | Frame, strategy: LocatorStrategy):
    if strategy.kind == LocatorKind.ROLE:
        candidate = scope.get_by_role(strategy.role or "button", name=strategy.value or None)
    elif strategy.kind == LocatorKind.TEXT:
        candidate = scope.get_by_text(strategy.value, exact=False)
    elif strategy.kind == LocatorKind.LABEL:
        candidate = scope.get_by_label(strategy.value)
    elif strategy.kind == LocatorKind.TEST_ID:
        candidate = scope.get_by_test_id(strategy.value)
    elif strategy.kind == LocatorKind.CSS:
        candidate = scope.locator(strategy.value)
    elif strategy.kind == LocatorKind.XPATH:
        candidate = scope.locator(f"xpath={strategy.value}")
    else:
        raise ValueError(f"Unknown locator kind: {strategy.kind}")
    return candidate.nth(strategy.nth) if strategy.nth is not None else candidate


def resolve_locator(page: Page, locator: Locator):
    """Descend any iframe path, then try primary then each fallback in order."""
    scope: Page | Frame = page
    for frame_selector in locator.frame_path:
        frame = page.frame_locator(frame_selector)
        scope = frame  # frame_locator returns a FrameLocator, compatible API subset

    last_error: Exception | None = None
    for strategy in locator.all_strategies():
        try:
            candidate = _resolve_strategy(scope, strategy)
            candidate.wait_for(state="attached", timeout=1500)
            return candidate
        except Exception as exc:  # noqa: BLE001 - we deliberately fall through
            last_error = exc
            continue
    raise LocatorResolutionError(f"No strategy resolved an element. Last error: {last_error}")


class BrowserSession:
    """One shared browser context for the lifetime of a discovery or replay run."""

    def __init__(self, base_url: str, headless: bool = False, engine: str = "chromium"):
        self.base_url = base_url
        self.headless = headless
        self.engine = engine
        self._playwright = None
        self.browser = None
        self.page: Page | None = None

    def start(self) -> Page:
        self._playwright = sync_playwright().start()
        browser_type = getattr(self._playwright, self.engine)
        self.browser = browser_type.launch(headless=self.headless)
        context = self.browser.new_context(base_url=self.base_url)
        self.page = context.new_page()
        return self.page

    def goto(self, url: str) -> None:
        self.page.goto(url, wait_until="load")

    def click(self, locator: Locator) -> None:
        resolve_locator(self.page, locator).click()

    def fill(self, locator: Locator, value: str) -> None:
        resolve_locator(self.page, locator).fill(value)

    def select_option(self, locator: Locator, value: str) -> None:
        resolve_locator(self.page, locator).select_option(value)

    def extract_text(self, locator: Locator) -> str:
        return resolve_locator(self.page, locator).inner_text()

    def is_visible(self, locator: Locator) -> bool:
        try:
            return resolve_locator(self.page, locator).is_visible()
        except LocatorResolutionError:
            return False

    def screenshot(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(path))

    def close(self) -> None:
        if self.browser:
            self.browser.close()
        if self._playwright:
            self._playwright.stop()
