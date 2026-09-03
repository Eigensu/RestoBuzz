"""Guard: every alert email template referenced in code must exist and render.

These templates have been lost from the working tree before. A missing file
does not crash — `_render_template` catches it — so the only symptom is an
alert that silently never arrives, with a FAILED audit row. This test turns
that into a build failure instead.
"""

import re
from pathlib import Path

import pytest

from app.services.alert_service import AlertService, templates_env

ALERT_SERVICE = Path(__file__).resolve().parents[2] / "app/services/alert_service.py"

# Context each alert passes to send_alert_email, beyond the shared base context.
TEMPLATE_CONTEXTS = {
    "template_approved.html": {"template_name": "promo_offer"},
    "template_rejected.html": {
        "template_name": "promo_offer",
        "rejection_reason": "Contains promotional content",
    },
    "unread_alert.html": {"unread_count": 7},
    "waba_disconnected.html": {},
    "campaign_failed.html": {
        "campaign_name": "Diwali Blast",
        "failure_reason": "Rate limit exceeded",
    },
}


def _referenced_templates() -> set[str]:
    source = ALERT_SERVICE.read_text()
    return set(re.findall(r'"([a-z_]+\.html)"', source))


def test_every_referenced_template_is_covered_by_this_test():
    """If a new alert is added, it must be added here too."""
    assert _referenced_templates() == set(TEMPLATE_CONTEXTS)


@pytest.mark.parametrize("template_name", sorted(TEMPLATE_CONTEXTS))
def test_alert_template_renders(template_name):
    """Renders under StrictUndefined, so a missing context var fails too."""
    _, email_context = AlertService._build_email_context(
        "Test Subject",
        {"name": "Test Restaurant"},
        TEMPLATE_CONTEXTS[template_name],
    )

    html = templates_env.get_template(f"email/{template_name}").render(**email_context)

    assert "Test Restaurant" in html
    assert "<html" in html.lower(), "template did not inherit from base.html"


def test_render_template_fails_soft_on_missing_file():
    """A missing template must never raise into the background task."""
    html, error = AlertService._render_template(
        "does_not_exist.html", "Subject", {"cta_url": "https://x", "restaurant_name": "R"}
    )
    assert html is None
    assert "Template error" in error
