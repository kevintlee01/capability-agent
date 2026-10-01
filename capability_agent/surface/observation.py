"""Build a compact accessibility-tree snapshot for the LLM to observe.

Uses Playwright's aria_snapshot (role + accessible name), not raw HTML, so
observation and replay targeting both still work on legacy markup with no
test IDs or semantic tags -- the common case per Section 1. Where a legacy
form exposes no accessible name at all (e.g. an unlabeled textbox), that
gap is visible right here in the outline, which is exactly the signal the
locator strategy needs to know when to fall back to a CSS/XPath strategy.
"""
from playwright.sync_api import Page


def accessibility_outline(page: Page) -> str:
    return page.locator("body").aria_snapshot()


def page_summary(page: Page) -> str:
    return f"URL: {page.url}\nTitle: {page.title()}\n\n{accessibility_outline(page)}"
