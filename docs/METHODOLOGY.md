# Analytical and experimentation methodology

## Measurement contract

Amounts are USD. Daily rows are at creative × audience × ad group × campaign × platform × landing-page grain. Conversions and leads represent the same synthetic demo event. MQLs are a subset of leads where mock CRM coverage is available. Revenue is attributed mock pipeline value. All platforms use a mock seven-day click convention; real platform attribution windows and view-through conversions often differ.

The comparison is the `window` calendar days ending on `end` (inclusive) versus the preceding `window` days. Default: August 10–23 against July 27–August 9, 2026. Early dataset dates have incomplete windows and suppress comparative trend flags.

| Metric | Formula |
|---|---|
| CTR | Total clicks / total impressions |
| CPC | Spend / clicks |
| CPM | Spend × 1,000 / impressions |
| CVR | Conversions / clicks |
| CPA | Spend / conversions |
| ROAS | Attributed revenue / spend |
| CPL | Spend / leads |
| Cost per MQL | Spend on CRM-covered rows / MQLs on those rows |
| MQL rate | MQLs / leads on covered rows |
| MQL coverage | Spend on covered rows / total spend |
| Frequency proxy | Sum(row frequency × impressions) / total impressions |

Zero denominators produce unknown values, not zeros or infinity. A rate in the API is a fraction (`0.04` = 4%). CPM is available in the full metrics drawer. Cross-channel totals are descriptive and do not deduplicate users or establish incremental return.

## Planning targets

| Platform | CPA target | ROAS target | CVR target | MQL/lead target |
|---|---:|---:|---:|---:|
| Google Ads | $75 | 3.0× | 4.5% | 50% |
| Meta Ads | $90 | 2.5× | 2.5% | 40% |
| LinkedIn Ads | $190 | 1.8× | 4.0% | 65% |

These are illustrative planning choices for synthetic B2B demo acquisition. They are intentionally different by platform; they are not market benchmarks. Adjust `TARGETS` and review tests when changing the fixture's business model.

## Health scoring

All components are 0–100 and disclosed. Rounded component values produce the weighted score.

- **Efficiency (35%)**: `50 × min(1, target CPA / observed CPA) + 50 × min(1, observed ROAS / target ROAS)`. Unknown CPA contributes zero. ROAS without spend contributes zero.
- **Conversion quality (20%)**: `100 × min(1, observed covered MQL rate / target MQL rate)`. Unknown quality gets a neutral 50 with a visible warning; it does not imply verified lead quality.
- **Trend (20%)**: 100 minus 30 for each CPA-rise, ROAS-fall or CTR-decline flag. Incomplete/low-click windows get a neutral 50.
- **Spend (10%)**: 20 when spend-without-results is flagged; 80 otherwise. This is a risk proxy, not business budget utilization.
- **Statistical confidence (15%)**: `100 × min(1, conversions/50) × min(1, clicks/500)`. Halved if comparison windows are incomplete. This volume score is not a probability that the recommendation is correct.

Scores can remain relatively high with a specific serious issue; inspect issue priority and evidence rather than treating the score as an approval rule. Low sample size and unknown quality must be reviewed independently.

## Issue thresholds

Trend rules require at least 100 clicks in each window and all expected calendar dates at campaign level. Relative change is `recent/prior - 1`; unknown or zero prior values do not yield an interpretable relative change.

| Issue | Trigger |
|---|---|
| CPA rising | CPA increase >20% |
| ROAS falling | ROAS decrease >15% |
| CTR declining | CTR decrease >15% |
| Frequency rising | Frequency proxy increase >20% |
| Weak CVR | Recent CVR <70% of platform target, ≥100 clicks |
| Spend without results | Spend increase >15%, conversions not increasing |
| Tracking check | ≥100 clicks with zero conversions, or comparable CVR falls >40% |
| Landing mismatch | Mock alignment score <50/100 |
| Creative fatigue | Creative frequency ≥3, ≥1,000 impressions in both windows, CTR decrease >15%, CPA increase >15%, complete campaign windows |

Issue confidence is Moderate when comparable windows have sufficient clicks and recent campaign conversions ≥30; otherwise Low. Fatigue confidence uses creative conversions ≥30. Rules are exploratory and can flag random variation. They do not use synthetic scenario labels.

A campaign with no issue flags, complete windows, ≥30 conversions, CPA below 85% of target and ROAS at/above target can receive a **human-reviewed increase proposal**. It never automatically receives more budget.

## Landing alignment

70% of the score is the fraction of mock keyword tokens found in the page headline/proposition. 30% reflects whether the page CTA contains the configured goal token. The ad-message field provides context for human review; this baseline does not perform semantic inference. Token matching can miss synonyms and overrate superficial repetition.

## Experiment design

1. Validate conversion definitions, tracking, CRM coverage and attribution lag.
2. Prioritize a business-relevant issue; group correlated signals to avoid duplicate or conflicting tests.
3. Pre-register one hypothesis, one primary KPI, fixed MDE, duration, sample target and secondary guardrails. Do not change these after observing results.
4. Use random assignment by user where possible and a stable 50/50 split. Avoid contamination from audience overlap, creative rotation and simultaneous landing/offer changes.
5. Require explicit human approval. Mark Testing only after a human starts the test outside this application.
6. Run at least two full weeks **and** the planned sample plus conversion lag. Avoid repeatedly checking for a winner. Account for seasonality.
7. Evaluate primary effect and uncertainty, lead quality, guardrails and multiple testing. For repeated exposure, use clustered/user-level inference. Cross-campaign causal comparisons need stronger designs than before/after ratios.
8. Record control/variant KPI values, sample counts, dates and human interpretation. Success cannot be entered with failed guardrails; underpowered results should be Inconclusive.

### Power approximation for CTR/CVR

The two-sided independent two-proportion normal approximation estimates observations **per arm**:

```text
p1 = baseline
p2 = p1 × (1 + relative MDE)
pbar = (p1 + p2) / 2
n = ceil((z(1-alpha/2) × sqrt(2×pbar×(1-pbar))
          + z(power) × sqrt(p1×(1-p1) + p2×(1-p2)))² / (p2-p1)²)
```

Defaults: alpha .05, power .80, relative MDE .15. Planning days are `max(14, ceil(2n / recent daily trials))`. CTR trials are impressions, CVR trials are clicks. This is a planning approximation; user assignment, repeated impressions, cluster effects, loss to attribution and traffic variance require adjustments. It is not a runtime significance calculator.

CPA and ROAS are ratios with variable costs/values: use a variance-aware bootstrap, geo experiment or matched-market design with pre-specified controls and adequate history. Budget pilots are capped at 10% in recommendation templates. Tracking validation is a diagnostic checklist rather than a randomized optimization test.

The descriptive 95% CVR Wilson interval assumes independent binomial trials. It is shown to communicate sampling uncertainty, not evidence of causality or a corrected multiple-comparison result.

## Budget simulation

**Decision-support simulation - not financial forecasting.**

Within each platform, choose the highest and lowest historical CPA among campaigns with complete windows and ≥30 conversions. Transfer up to the slider's fraction of donor spend (0–30%), capped at 20% of recipient spend. Do not transfer if the donor CPA is within 10% of the recipient CPA. Preserve total spend exactly and leave ineligible campaigns unchanged.

The illustrative conversion scenario is simulated spend / historical CPA. A sensitivity case assumes CPA is 20% worse. There is no prediction model, learning-phase model, diminishing returns curve, incrementality estimate or real revenue forecast. Before applying a scenario manually, assess marginal CPA, qualified pipeline, pacing, channel strategy and auction saturation.

## Human review and persistence

Recommendation IDs hash version, evidence end date, window length, campaign ID and issue. Generating the same set is idempotent and never resets decisions. New windows create separate proposals with dated evidence. Writes use SQLite transactions with expected-version checks; stale updates return HTTP 409.

Allowed transitions:

```text
Proposed → Approved → Testing → Completed
    └────────┴─────────┴──────→ Rejected
```

Reviewer and rationale are required. Final results are required for Completed and may only be supplied then. Completed/Rejected are terminal. This is a local, unauthenticated review register. Identity is self-reported and direct database access can alter records; it is not a production compliance system.
