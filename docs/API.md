# API guide

Run `uvicorn paid_media.api:app --port 8000`; interactive contracts at `http://localhost:8000/docs`. No authentication is provided: run locally. No route can change advertising campaigns or budgets.

| Method | Route | Purpose |
|---|---|---|
| GET | `/health` | Service and explicit synthetic/execution markers |
| GET | `/metadata` | Date range, row count and platforms |
| GET | `/analysis?end=2026-08-23&window=14&platform=Meta%20Ads` | Metrics, health, issues, creative fatigue and page alignment |
| GET | `/series?platform=Meta%20Ads` | Daily summed volume/cost series |
| GET | `/recommendations?status=Proposed` | Persisted proposals and decisions |
| POST | `/recommendations/generate?end=2026-08-23&window=14` | Save proposals for this window idempotently |
| PATCH | `/recommendations/{id}` | Record a human review; optimistic version check |
| GET | `/recommendations/{id}/history` | Ordered decision audit history |
| GET | `/budget-simulation?shift_fraction=0.1` | Spend-conserving scenario; accepts end/window too |
| POST | `/creative/draft` | Generate offline or explicitly opted-in AI drafts |

Date must be in the synthetic dataset; windows are 7–28 days. Invalid scope returns 422. Missing proposal IDs return 404. Stale versions or forbidden transitions return 409. No ingestion/upload route exists. Analyses are read-only; generating proposals and decisions writes the local SQLite review register.

## Human approval

```json
{
  "status": "Approved",
  "reviewer": "Demo analyst",
  "notes": "Reviewed traffic quality and fixed the test budget cap.",
  "expected_version": 1
}
```

Use the returned version for the next transition. To complete a Testing recommendation, also include:

```json
{
  "status": "Completed",
  "reviewer": "Demo analyst",
  "notes": "Reviewed final test evidence after attribution lag.",
  "expected_version": 3,
  "result": {
    "primary_kpi": "CVR",
    "baseline_value": 0.04,
    "variant_value": 0.047,
    "control_sample": 18000,
    "variant_sample": 18000,
    "started_on": "2026-08-24",
    "ended_on": "2026-09-14",
    "outcome": "Inconclusive",
    "guardrails_passed": true,
    "notes": "Observed improvement; adjust inference for repeated users before deciding."
  }
}
```

The primary KPI must match the proposal. Dates must be ordered. Samples must be positive. Rates are fractions bounded 0–1; amounts/ratios are nonnegative finite values. Success requires guardrails passed. Results are human-reported; the API does not calculate causal significance or declare winners.

## Creative brief

```json
{
  "audience": "Revenue operations leaders",
  "product": "Mock revenue analytics software",
  "brand_tone": "Professional",
  "campaign_goal": "Book a demo",
  "use_ai": false
}
```

Returns three or more headlines, primary-text variants, CTAs and angles, plus source and review requirement. Optional AI requires server-side enablement/key and `use_ai=true`; provider/network/schema failures return 422 without echoing credentials.

## Simple client example

```python
import httpx

base = "http://localhost:8000"
report = httpx.get(f"{base}/analysis", timeout=15).json()
proposals = httpx.get(f"{base}/recommendations", timeout=15).json()
proposal = next(r for r in proposals if r["status"] == "Proposed")
response = httpx.patch(
    f"{base}/recommendations/{proposal['id']}",
    json={
        "status": "Approved",
        "reviewer": "Demo analyst",
        "notes": "Reviewed the experiment and guardrails.",
        "expected_version": proposal["version"],
    },
    timeout=15,
)
response.raise_for_status()
```
