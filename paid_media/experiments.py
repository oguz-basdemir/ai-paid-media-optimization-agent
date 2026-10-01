"""Evidence-led recommendations and pre-registered experiment templates."""

import hashlib
import math
from statistics import NormalDist

CATALOG = {
    "cpa_rising": (
        "Investigate audience",
        "Lower-intent traffic is raising acquisition cost.",
        "Randomize eligible users between the existing audience and a tightened intent segment.",
        "CPA",
        "MQL rate",
        "Reduce CPA by 15% without lowering MQL rate.",
    ),
    "roas_falling": (
        "Improve offer",
        "The current offer attracts leads with lower revenue potential.",
        "A/B test a use-case-specific offer against the current offer.",
        "ROAS",
        "CVR",
        "Improve ROAS by 15% with no more than 5% relative CVR loss.",
    ),
    "ctr_declining": (
        "Test new headline",
        "The headline no longer resonates with the target audience.",
        "Randomize users between the existing headline and one benefit-led headline.",
        "CTR",
        "CVR",
        "Improve CTR by 15% with no more than 5% relative CVR loss.",
    ),
    "frequency_rising": (
        "Investigate audience",
        "Audience saturation is limiting incremental response.",
        "Test a fresh eligible audience segment with the same creative and offer.",
        "CPA",
        "Reach",
        "Reduce CPA by 15% while maintaining qualified conversion volume.",
    ),
    "weak_cvr": (
        "Improve offer",
        "The offer or page friction is reducing conversion rate.",
        "A/B test a shorter demo form with the same offer and traffic split.",
        "CVR",
        "CPA",
        "+15% CVR with stable traffic quality and no more than 5% CPA increase.",
    ),
    "spend_without_results": (
        "Review budget reduction",
        "Marginal inventory is less efficient than the baseline.",
        "Review a capped 10% budget reduction in a matched-market pilot after tracking validation.",
        "CPA",
        "Conversions",
        "Reduce CPA by 10% with no more than 5% conversion volume loss.",
    ),
    "tracking_check": (
        "Validate tracking",
        "A measurement issue is hiding conversions.",
        "Manually compare synthetic event logs and CRM counts; verify deduplication and attribution.",
        "Event match rate",
        "Duplicate rate",
        "At least 95% event match and less than 1% duplicate events.",
    ),
    "landing_mismatch": (
        "Change landing page",
        "Landing-page mismatch is reducing conversion rate.",
        "Create a landing page aligned with ad messaging and randomize eligible users 50/50.",
        "CVR",
        "CPA",
        "+15% CVR with stable traffic quality and no more than 5% CPA increase.",
    ),
    "creative_fatigue": (
        "Refresh creative",
        "Repeated exposure to the same creative is reducing response.",
        "Randomize eligible users between the existing creative and a fresh visual with the same offer.",
        "CTR",
        "CPA",
        "+15% CTR with no more than 5% CPA increase and stable MQL rate.",
    ),
    "efficient_scale": (
        "Review budget increase",
        "An efficient campaign may absorb limited incremental spend.",
        "Review a capped 10% increase in a matched-market pilot with a fixed stop-loss.",
        "CPA",
        "MQLs",
        "Increase MQLs by 10% while keeping CPA within the platform target.",
    ),
}


def sample_size(baseline: float, relative_lift: float = 0.15, power: float = 0.8, alpha: float = 0.05) -> int:
    """Two-sided two-proportion normal approximation; sample is independent trials per arm."""
    p1, p2 = baseline, baseline * (1 + relative_lift)
    if not (0 < p1 < p2 < 1 and 0 < alpha < 1 and 0.5 < power < 1):
        raise ValueError("Baseline and uplift must produce probabilities strictly between 0 and 1.")
    avg = (p1 + p2) / 2
    z_alpha = NormalDist().inv_cdf(1 - alpha / 2)
    z_power = NormalDist().inv_cdf(power)
    return math.ceil(
        (
            (z_alpha * math.sqrt(2 * avg * (1 - avg)) + z_power * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2)))
            / (p2 - p1)
        )
        ** 2
    )


def recommendations(report: dict) -> list[dict]:
    output = []
    for campaign in report["campaigns"]:
        issues = list(campaign["issues"])
        m = campaign["metrics"]
        if (
            not issues
            and campaign["complete_windows"]
            and m["conversions"] >= 30
            and m["cpa"] is not None
            and m["cpa"] < campaign["targets"]["cpa"] * 0.85
            and (m["roas"] or 0) >= campaign["targets"]["roas"]
        ):
            issues.append(
                {
                    "code": "efficient_scale",
                    "reason": "Historical efficiency supports a cautious scale test",
                    "evidence": {"cpa": m["cpa"], "roas": m["roas"]},
                    "severity": "Low",
                    "confidence": "Moderate",
                }
            )
        for issue in issues:
            action, hypothesis, test, primary, secondary, success = CATALOG[issue["code"]]
            stable = (
                f"v1:{report['end_date']}:{report['window_days']}:{campaign['campaign_id']}:{issue['code']}"
            )
            rid = hashlib.sha256(stable.encode()).hexdigest()[:20]
            baseline = m.get(primary.lower())
            planning = None
            if primary in {"CTR", "CVR"} and baseline and baseline * 1.15 < 1:
                n = sample_size(baseline)
                daily_trials = m["impressions" if primary == "CTR" else "clicks"] / report["window_days"]
                planning = {
                    "baseline": baseline,
                    "relative_mde": 0.15,
                    "alpha": 0.05,
                    "power": 0.80,
                    "trials_per_arm": n,
                    "trial_unit": "impressions" if primary == "CTR" else "clicks",
                    "estimated_days": max(14, math.ceil(2 * n / max(daily_trials, 0.01))),
                    "caveat": "Approximation only. Assign by user; adjust for repeat users, clustering and conversion lag.",
                }
            output.append(
                {
                    "id": rid,
                    "campaign_id": campaign["campaign_id"],
                    "campaign": campaign["campaign"],
                    "platform": campaign["platform"],
                    "issue": issue["code"],
                    "action": action,
                    "reason": issue["reason"],
                    "evidence": issue["evidence"],
                    "severity": issue["severity"],
                    "confidence": issue["confidence"],
                    "as_of": report["end_date"],
                    "window_days": report["window_days"],
                    "status": "Proposed",
                    "requires_human_approval": True,
                    "experiment": {
                        "hypothesis": hypothesis,
                        "test": test,
                        "primary_kpi": primary,
                        "secondary_kpi": secondary,
                        "success_criteria": success,
                        "design": "Diagnostic checklist"
                        if issue["code"] == "tracking_check"
                        else "Matched-market pilot"
                        if primary in {"CPA", "ROAS"}
                        else "Randomized A/B test",
                        "guardrails": [
                            "Stable MQL rate and attribution settings",
                            "Fixed budget cap",
                            "Stop if CPA rises >20% after minimum sample and conversion lag",
                        ],
                        "duration": "At least 14 days, then complete planned sample and attribution lag; no early win calls.",
                        "planning": planning,
                        "decision_rule": "Pre-register one primary KPI. Use user-level inference; correct for multiple tests. "
                        "Call inconclusive if underpowered or guardrails fail.",
                    },
                }
            )
    return sorted(output, key=lambda r: ({"High": 0, "Medium": 1, "Low": 2}[r["severity"]], r["id"]))


def simulate(report: dict, shift_fraction: float = 0.10) -> dict:
    if not 0 <= shift_fraction <= 0.30:
        raise ValueError("Redistribution must be between 0% and 30%.")
    rows = []
    # Never move funds across platforms: their auctions, lead quality and attribution differ.
    for platform in sorted({c["platform"] for c in report["campaigns"]}):
        campaigns = [c for c in report["campaigns"] if c["platform"] == platform]
        eligible = [
            c
            for c in campaigns
            if c["complete_windows"] and c["metrics"]["conversions"] >= 30 and c["metrics"]["cpa"] is not None
        ]
        donor, recipient = None, None
        if len(eligible) >= 2:
            donor = max(eligible, key=lambda c: c["metrics"]["cpa"])
            recipient = min(eligible, key=lambda c: c["metrics"]["cpa"])
            if donor["metrics"]["cpa"] <= recipient["metrics"]["cpa"] * 1.1:
                donor, recipient = None, None
        amount = (
            min(donor["metrics"]["spend"] * shift_fraction, recipient["metrics"]["spend"] * 0.20)
            if donor and recipient
            else 0.0
        )
        for c in campaigns:
            m = c["metrics"]
            delta = -amount if c is donor else amount if c is recipient else 0.0
            assumed = (m["spend"] + delta) / m["cpa"] if m["cpa"] else None
            rows.append(
                {
                    "campaign_id": c["campaign_id"],
                    "campaign": c["campaign"],
                    "platform": platform,
                    "historical_spend": m["spend"],
                    "simulated_spend": m["spend"] + delta,
                    "budget_delta": delta,
                    "historical_cpa": m["cpa"],
                    "constant_cpa_conversions": assumed,
                    "cpa_20pct_worse_conversions": assumed / 1.2 if assumed is not None else None,
                    "eligible": c in eligible,
                }
            )
    return {
        "label": "Decision-support simulation - not financial forecasting.",
        "rows": rows,
        "shift_fraction": shift_fraction,
        "requires_human_approval": True,
        "assumptions": [
            "Within-platform allocation only; total spend conserved.",
            "Donor shift capped at 30%; recipient increase capped at 20%.",
            "At least 30 conversions and complete windows required.",
            "Constant historical CPA is a scenario assumption, not a prediction.",
            "Auction dynamics, saturation, incrementality and revenue lag are not modeled.",
        ],
    }
