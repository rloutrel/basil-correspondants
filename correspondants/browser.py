"""Browser adapter boundary for the read-page capability.

The real implementation will drive Playwright. Tests replace this module's
functions with fakes — no test ever launches a browser or touches the
network. Playwright itself is intentionally not a dependency in this phase;
the adapter interface is frozen so the real driver can be dropped in later.
"""

class BrowserError(Exception):
    """Navigation or extraction infrastructure failure."""


def fetch_page(url, wait_for_selector=None, timeout_ms=None):
    """Load a page and return its content for extraction.

    Phase 1 stub: raise so no accidental network access happens; the real
    Playwright driver is a later delivery and will be injected here.
    """
    raise BrowserError(
        "Playwright driver is not enabled in this phase; "
        "fetch_page must be mocked in tests."
    )


def extract_selector(page_content, selector, selector_type="css", attribute=None):
    """Return (value, found) for one selector against page content.

    Phase 1 stub, same rationale as fetch_page.
    """
    raise BrowserError(
        "Playwright driver is not enabled in this phase; "
        "extract_selector must be mocked in tests."
    )
