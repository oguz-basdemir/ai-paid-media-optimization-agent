# Contributing

Use Python 3.12+, create a virtual environment and follow the README. Run `pytest -q`, `ruff check .` and `ruff format --check .` before submitting changes. Docker smoke checks run separately in CI. Regenerate seed-42 samples only when deliberately changing the fixture, and describe changes in a PR.

Keep analytical rules explainable and avoid using the fixture scenario labels as model inputs. Add tests for changed metric semantics, approval transitions and safety boundaries. Keep missing CRM data distinct from zero. New experiment types must include a hypothesis, meaningful KPI, guardrails and an explicit human decision point.

Do not add real account data, ad-account credentials, live import routes, automatic campaign writes or autonomous budget execution. Optional model calls may draft synthetic copy; they must never decide approvals or run account changes. Review generated copy for unsupported claims.

For a PR, describe the concrete behavior change, the marketing rationale, verification and any statistical limitations.
