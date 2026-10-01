"""Run actual Streamlit views against an isolated FastAPI fixture, without a live server."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import paid_media.client

APP_PATH = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")


@pytest.mark.parametrize(
    "section",
    [
        "Cross-Channel Overview",
        "Google Ads",
        "Meta",
        "LinkedIn",
        "Campaign Health",
        "Creative Fatigue",
        "Experiments",
        "Recommendations",
        "Creative Studio",
        "Landing-Page Analysis",
        "Budget Simulator",
    ],
)
def test_dashboard_views(client, monkeypatch, section):
    def transport(method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    monkeypatch.setattr(paid_media.client, "call", transport)
    app = AppTest.from_file(APP_PATH, default_timeout=20).run()
    app.sidebar.radio[0].set_value(section).run()
    assert not app.exception
    assert not app.error
    assert app.title[0].value == section


def test_creative_form_submission(client, monkeypatch):
    monkeypatch.setattr(
        paid_media.client, "call", lambda method, path, **kw: client.request(method, path, **kw).json()
    )
    app = AppTest.from_file(APP_PATH, default_timeout=20).run()
    app.sidebar.radio[0].set_value("Creative Studio").run()
    app.button[0].click().run()
    assert not app.exception
    assert "creative" in app.session_state


def test_api_unavailable_is_actionable(monkeypatch):
    def unavailable(*args, **kwargs):
        raise RuntimeError("API unavailable. Start uvicorn paid_media.api:app --port 8000, then refresh.")

    monkeypatch.setattr(paid_media.client, "call", unavailable)
    app = AppTest.from_file(APP_PATH).run()
    assert not app.exception
    assert "API unavailable" in app.error[0].value


def test_dashboard_records_approval(client, monkeypatch):
    monkeypatch.setattr(
        paid_media.client, "call", lambda method, path, **kw: client.request(method, path, **kw).json()
    )
    app = AppTest.from_file(APP_PATH, default_timeout=20).run()
    app.sidebar.radio[0].set_value("Recommendations").run()
    next(w for w in app.selectbox if w.label == "Next status").set_value("Approved").run()
    next(w for w in app.text_input if w.label == "Reviewer").set_value("UI demo reviewer")
    next(w for w in app.text_input if w.label == "Decision rationale").set_value(
        "Reviewed KPI and budget guardrails"
    )
    next(w for w in app.button if w.label == "Record human decision").click().run()
    assert not app.exception and not app.error
    records = client.get("/recommendations").json()
    assert sum(r["status"] == "Approved" for r in records) == 1
