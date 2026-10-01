import pytest
from pydantic import ValidationError

from paid_media.api import TestResult as ResultModel
from paid_media.creative import CreativeBrief, draft


def review(client, r, status, **extra):
    return client.patch(
        f"/recommendations/{r['id']}",
        json={
            "status": status,
            "reviewer": "Demo analyst",
            "notes": "Reviewed evidence and fixed the experiment guardrails.",
            "expected_version": r["version"],
            **extra,
        },
    )


def result(kpi):
    return {
        "primary_kpi": kpi,
        "baseline_value": 0.04,
        "variant_value": 0.047,
        "control_sample": 18000,
        "variant_sample": 18000,
        "started_on": "2026-08-24",
        "ended_on": "2026-09-14",
        "outcome": "Inconclusive",
        "guardrails_passed": True,
        "notes": "Observed lift; user-level confidence and conversion lag still need review.",
    }


def test_read_api_and_explicit_no_execution(client):
    health = client.get("/health").json()
    assert health["synthetic_only"] and not health["campaign_execution_enabled"]
    report = client.get("/analysis").json()
    assert len(report["campaigns"]) == 12
    assert len(client.get("/analysis?platform=Meta%20Ads").json()["campaigns"]) == 4
    assert client.get("/series").status_code == 200
    assert client.get("/metadata").json()["rows"] == 2016
    assert client.get("/budget-simulation").status_code == 200
    paths = client.get("/openapi.json").json()["paths"]
    assert not any("execute" in p or "campaigns" in p for p in paths)
    assert client.post("/campaigns/execute").status_code == 404


@pytest.mark.parametrize("query", ["window=0", "window=40", "end=2020-01-01", "platform=TikTok"])
def test_invalid_analysis_scope(client, query):
    assert client.get("/analysis?" + query).status_code == 422


def test_full_human_workflow_audit_and_idempotent_regeneration(client):
    r = client.get("/recommendations").json()[0]
    assert review(client, r, "Testing").status_code == 409
    approved = review(client, r, "Approved").json()
    assert approved["status"] == "Approved"
    assert review(client, r, "Rejected").status_code == 409  # stale version
    client.post("/recommendations/generate")
    saved = next(x for x in client.get("/recommendations").json() if x["id"] == r["id"])
    assert saved["status"] == "Approved" and saved["version"] == approved["version"]
    testing = review(client, approved, "Testing").json()
    assert review(client, testing, "Completed").status_code == 422
    completed = review(client, testing, "Completed", result=result(r["experiment"]["primary_kpi"])).json()
    assert completed["status"] == "Completed" and completed["result"]["outcome"] == "Inconclusive"
    assert review(client, completed, "Approved").status_code == 409
    events = client.get(f"/recommendations/{r['id']}/history").json()
    assert [e["to_status"] for e in events] == ["Approved", "Testing", "Completed"]
    assert all(e["reviewer"] == "Demo analyst" for e in events)


def test_rejection_and_required_reviewer(client):
    r = client.get("/recommendations").json()[0]
    response = client.patch(
        f"/recommendations/{r['id']}",
        json={"status": "Approved", "reviewer": " ", "notes": " ", "expected_version": 1},
    )
    assert response.status_code == 422
    rejected = review(client, r, "Rejected").json()
    assert rejected["status"] == "Rejected"
    assert review(client, rejected, "Testing").status_code == 409
    assert client.get("/recommendations/missing/history").status_code == 404


def test_result_validation_and_preregistered_kpi(client):
    values = result("CVR")
    with pytest.raises(ValidationError):
        ResultModel(**{**values, "variant_value": 1.2})
    with pytest.raises(ValidationError):
        ResultModel(**{**values, "outcome": "Success", "guardrails_passed": False})
    with pytest.raises(ValidationError):
        ResultModel(**{**values, "ended_on": "2025-01-01"})
    r = client.get("/recommendations").json()[0]
    approved = review(client, r, "Approved").json()
    testing = review(client, approved, "Testing").json()
    assert review(client, testing, "Completed", result=result("invented KPI")).status_code == 422


def test_creative_brief_offline_and_ai_opt_in(client, monkeypatch):
    brief = {
        "audience": "Marketing leaders",
        "product": "Demo analytics",
        "brand_tone": "Bold",
        "campaign_goal": "Book a demo",
    }
    output = client.post("/creative/draft", json=brief).json()
    assert output["requires_human_review"] and len(output["headlines"]) == 3
    assert "Rethink" in output["headlines"][0]
    assert "Demo analytics" in output["primary_text"][0]
    monkeypatch.setenv("ENABLE_AI", "false")
    assert client.post("/creative/draft", json={**brief, "use_ai": True}).status_code == 422


def test_optional_ai_success_and_malformed_response(monkeypatch):
    import httpx

    monkeypatch.setenv("ENABLE_AI", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "fake-synthetic-test-key")
    captured = {}

    def mock_post(url, **kwargs):
        captured.update(kwargs)
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"headlines":["A","B","C"],"primary_text":["D","E","F"],"ctas":["G","H","I"],"angles":["J","K","L"]}'
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx, "post", mock_post)
    brief = CreativeBrief(
        audience="Mock audience",
        product="Mock product",
        brand_tone="Professional",
        campaign_goal="Demo",
        use_ai=True,
    )
    assert draft(brief)["source"] == "AI-assisted draft"
    assert "spend" not in captured["json"]["messages"][1]["content"]
    monkeypatch.setattr(
        httpx, "post", lambda url, **kwargs: httpx.Response(200, request=httpx.Request("POST", url), json={})
    )
    with pytest.raises(ValueError, match="invalid draft JSON"):
        draft(brief)
