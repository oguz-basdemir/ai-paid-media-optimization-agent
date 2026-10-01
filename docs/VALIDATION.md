# Verification record

Validation performed October 1, 2026 on Windows with Python 3.12.14.

| Check | Result |
|---|---|
| pytest | 39 passed |
| Analytical checks | Reproducibility, ratios of totals, missing MQL coverage, zero denominators, window boundaries, health explanation, issue/fatigue detection, sample planning and simulation constraints |
| API checks | All read surfaces, scope validation, synthetic/no-execution markers, approval/result validation, stale-update conflicts, idempotent regeneration and mocked AI requests |
| Persistence checks | SQLite reopen and concurrent reviewers; exactly one decision wins a stale-version race |
| Streamlit checks | All 11 workspace views, creative form, approval form and actionable unavailable-API state |
| Ruff | Lint passes; formatting applied |
| pip check | No broken requirements |
| Live service smoke | 12 campaigns, 3 likely-fatigued creatives and 42 saved proposals from committed synthetic fixtures |
| Browser verification | Actual running dashboard captured with headless Chrome; screenshots inspected |
| Docker | Configuration supplied; not executed locally because Docker is unavailable |
| Live AI provider | Not called; success/error behavior tested with mocked compatible responses |

The locked reference environment emits one upstream Starlette warning that httpx-backed TestClient is deprecated in favor of httpx2. Tests still pass; no deprecation warnings are hidden in the default test command.

CI runs lint and pytest on Python 3.12/3.13 and separately builds, starts and health-checks Docker Compose on Linux. Those remote jobs are configured but have not been run by this local build.

To reproduce screenshots, start the demo and run:

```bash
playwright install chromium
python scripts/capture_screenshots.py
# Existing Chrome: python scripts/capture_screenshots.py --channel chrome
# Custom launcher ports: append --url http://127.0.0.1:8510
```

Screenshots are synthetic demonstration outputs, not claims of actual advertising performance. Tests validate implementation invariants; they do not validate campaign causality, predictive accuracy or business ROI.
