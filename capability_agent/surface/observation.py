"""Compact accessibility-tree snapshot for the LLM: role + accessible name, so observation still works on legacy markup with no test IDs or ARIA."""
from playwright.sync_api import Page


def accessibility_outline(page: Page) -> str:
    return page.locator("body").aria_snapshot()


def page_summary(page: Page) -> str:
    return f"URL: {page.url}\nTitle: {page.title()}\n\n{accessibility_outline(page)}"
