"""Smoke tests for the Streamlit UI wiring.

Uses Streamlit's AppTest harness so the app can be exercised without a browser.
Runs whether or not FalkorDB is available: when the database is down the views
must degrade gracefully instead of raising.
"""

import os

import pytest
from streamlit.testing.v1 import AppTest

APP_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")

VIEWS = ["Query Console", "Incident Triage", "Graph Explorer", "Cypher Lab", "Runbooks"]


def test_app_initial_run_has_no_exception():
    at = AppTest.from_file(APP_PATH, default_timeout=120).run()
    assert not at.exception
    assert at.radio
    assert at.radio[0].options == VIEWS


@pytest.mark.parametrize("view", VIEWS)
def test_each_view_renders_without_exception(view):
    at = AppTest.from_file(APP_PATH, default_timeout=120).run()
    at.radio[0].set_value(view).run()
    assert not at.exception


def test_followups_handle_singular_entity_keys():
    """The agent reports entities as singular strings for most intents."""
    import app

    followups = app.derive_followups({"intent": "owner", "entities": {"service": "Payments API"}})
    prompts = [prompt for _, prompt in followups]
    assert followups
    assert any("Payments API" in prompt for prompt in prompts)


def test_followups_handle_plural_entity_keys():
    """Fallback intent path reports entities as plural lists."""
    import app

    response = {"intent": "investigate", "entities": {"incidents": ["INC-101"], "services": ["Payments API"]}}
    followups = app.derive_followups(response)
    prompts = [prompt for _, prompt in followups]
    assert any("INC-101" in prompt for prompt in prompts)
