"""Ratio-of-sums metrics, descriptive confidence and explainable campaign diagnoses."""

import math
import re

import pandas as pd

from paid_media.data import TARGETS


def ratio(numerator: float, denominator: float) -> float | None:
    return float(numerator / denominator) if denominator > 0 else None


def metrics(frame: pd.DataFrame) -> dict:
    totals = {
        k: float(frame[k].sum())
        for k in ["impressions", "clicks", "spend", "conversions", "revenue", "leads"]
    }
    t = totals
    # Missing CRM rows are unknown, never zero. CPL/MQL denominators must share coverage.
    covered = frame[frame.mqls.notna()]
    t.update(
        {
            "ctr": ratio(t["clicks"], t["impressions"]),
            "cpc": ratio(t["spend"], t["clicks"]),
            "cpm": ratio(t["spend"] * 1000, t["impressions"]),
            "cvr": ratio(t["conversions"], t["clicks"]),
            "cpa": ratio(t["spend"], t["conversions"]),
            "roas": ratio(t["revenue"], t["spend"]),
            "cpl": ratio(t["spend"], t["leads"]),
            "mqls": float(covered.mqls.sum()) if len(covered) else None,
            "cost_per_mql": ratio(float(covered.spend.sum()), float(covered.mqls.sum())),
            "mql_rate": ratio(float(covered.mqls.sum()), float(covered.leads.sum())),
            "mql_spend_coverage": ratio(float(covered.spend.sum()), t["spend"]),
            "frequency": ratio(float((frame.frequency * frame.impressions).sum()), t["impressions"]),
        }
    )
    return t


def wilson(successes: float, trials: float) -> list[float | None]:
    if trials <= 0:
        return [None, None]
    z = 1.96
    p = successes / trials
    center = (p + z * z / (2 * trials)) / (1 + z * z / trials)
    half = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / (1 + z * z / trials)
    return [max(0, center - half), min(1, center + half)]


def change(current, prior) -> float | None:
    return (current / prior - 1) if current is not None and prior is not None and prior > 0 else None


def windows(frame: pd.DataFrame, end: str, window: int = 14) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = pd.to_datetime(frame.date)
    finish = pd.Timestamp(end)
    return (
        frame[(dates > finish - pd.Timedelta(days=window)) & (dates <= finish)],
        frame[
            (dates > finish - pd.Timedelta(days=2 * window)) & (dates <= finish - pd.Timedelta(days=window))
        ],
    )


def landing_alignment(page: dict) -> dict:
    tokens = set(re.findall(r"[a-z]+", (page["headline"] + " " + page["proposition"]).lower()))
    matched = [kw for kw in page["keywords"] if kw.lower() in tokens]
    keyword_score = len(matched) / max(1, len(page["keywords"]))
    cta_match = page["goal"].lower() in page["cta"].lower()
    score = round(100 * (0.7 * keyword_score + 0.3 * cta_match))
    return {
        **page,
        "alignment_score": score,
        "matched_keywords": matched,
        "cta_matches_goal": cta_match,
        "reason": f"{len(matched)}/{len(page['keywords'])} ad keyword tokens match; "
        f"CTA {'supports' if cta_match else 'does not support'} the {page['goal']} goal.",
        "method": "Explainable token/CTA heuristic on mock metadata; no live-page crawl.",
    }


def diagnose(frame: pd.DataFrame, pages: list[dict], end: str | None = None, window: int = 14) -> dict:
    end = end or str(frame.date.max())
    recent, previous = windows(frame, end, window)
    page_map = {p["campaign_id"]: landing_alignment(p) for p in pages}
    campaigns, fatigue = [], []
    for cid, group in recent.groupby("campaign_id", sort=True):
        prior_group = previous[previous.campaign_id == cid]
        now, before = metrics(group), metrics(prior_group)
        platform = str(group.platform.iloc[0])
        target = TARGETS[platform]
        deltas = {k: change(now[k], before[k]) for k in ["cpa", "roas", "ctr", "cvr", "spend", "frequency"]}
        complete = group.date.nunique() == window and prior_group.date.nunique() == window
        enough = complete and now["clicks"] >= 100 and before["clicks"] >= 100
        issues = []

        def flag(code, reason, evidence, severity="Medium", issues=issues, enough=enough, now=now):
            issues.append(
                {
                    "code": code,
                    "reason": reason,
                    "evidence": evidence,
                    "severity": severity,
                    "confidence": "Moderate" if enough and now["conversions"] >= 30 else "Low",
                }
            )

        for key, threshold, code, reason in [
            ("cpa", 0.20, "cpa_rising", "Acquisition costs are rising"),
            ("roas", -0.15, "roas_falling", "Attributed return is declining"),
            ("ctr", -0.15, "ctr_declining", "Ad engagement is declining"),
            ("frequency", 0.20, "frequency_rising", "Audience exposure is increasing"),
        ]:
            delta = deltas[key]
            if enough and delta is not None and (delta > threshold if threshold > 0 else delta < threshold):
                flag(
                    code,
                    reason,
                    {"metric": key, "current": now[key], "previous": before[key], "relative_change": delta},
                )
        if now["clicks"] >= 100 and now["cvr"] is not None and now["cvr"] < 0.7 * target["cvr"]:
            flag(
                "weak_cvr",
                "Conversion rate is below the platform planning target",
                {"cvr": now["cvr"], "target": target["cvr"], "clicks": now["clicks"]},
                "High",
            )
        if (
            enough
            and deltas["spend"] is not None
            and deltas["spend"] > 0.15
            and now["conversions"] <= before["conversions"]
        ):
            flag(
                "spend_without_results",
                "Spend is growing without more conversions",
                {
                    "spend_change": deltas["spend"],
                    "conversions": now["conversions"],
                    "previous_conversions": before["conversions"],
                },
                "High",
            )
        if now["clicks"] >= 100 and (
            now["conversions"] == 0 or (enough and deltas["cvr"] is not None and deltas["cvr"] < -0.40)
        ):
            flag(
                "tracking_check",
                "Conversion reporting dropped sharply; validate tracking before optimization",
                {"clicks": now["clicks"], "conversions": now["conversions"], "cvr_change": deltas["cvr"]},
                "High",
            )
        page = page_map[cid]
        if page["alignment_score"] < 50:
            flag(
                "landing_mismatch",
                "Ad promise and landing-page proposition do not align",
                {"alignment_score": page["alignment_score"], "reason": page["reason"]},
                "High",
            )
        # Detect fatigue at creative grain, avoiding an aggregate-only diagnosis.
        for creative, cg in group.groupby("creative"):
            pg = prior_group[prior_group.creative == creative]
            cm, pm = metrics(cg), metrics(pg)
            ctr_delta, cpa_delta = change(cm["ctr"], pm["ctr"]), change(cm["cpa"], pm["cpa"])
            if (
                complete
                and cm["impressions"] >= 1000
                and pm["impressions"] >= 1000
                and cm["frequency"] >= 3
                and ctr_delta is not None
                and ctr_delta < -0.15
                and cpa_delta is not None
                and cpa_delta > 0.15
            ):
                fatigue.append(
                    {
                        "campaign_id": cid,
                        "creative": creative,
                        "platform": platform,
                        "frequency": cm["frequency"],
                        "ctr_change": ctr_delta,
                        "cpa_change": cpa_delta,
                        "impressions": cm["impressions"],
                        "confidence": "Moderate" if cm["conversions"] >= 30 else "Low",
                    }
                )
        affected = [f["creative"] for f in fatigue if f["campaign_id"] == cid]
        if affected:
            flag(
                "creative_fatigue",
                "Likely creative fatigue: repeated exposure and deteriorating response",
                {"creatives": affected, "frequency": now["frequency"]},
                "High",
            )
        efficiency = 0 if now["cpa"] is None else 50 * min(1, target["cpa"] / max(now["cpa"], 0.01))
        efficiency += 50 * min(1, (now["roas"] or 0) / target["roas"])
        quality = 100 * min(1, now["mql_rate"] / target["mql_rate"]) if now["mql_rate"] is not None else 50.0
        trend = 50.0
        if enough:
            adverse = sum(
                1
                for k in ["cpa_rising", "roas_falling", "ctr_declining"]
                if any(i["code"] == k for i in issues)
            )
            trend = max(0, 100 - adverse * 30)
        spend_score = 20.0 if any(i["code"] == "spend_without_results" for i in issues) else 80.0
        confidence = 100 * min(1, now["conversions"] / 50) * min(1, now["clicks"] / 500)
        if not complete:
            confidence *= 0.5
        components = {
            "efficiency": efficiency,
            "conversion_quality": quality,
            "trend": trend,
            "spend": spend_score,
            "statistical_confidence": confidence,
        }
        weights = {
            "efficiency": 0.35,
            "conversion_quality": 0.20,
            "trend": 0.20,
            "spend": 0.10,
            "statistical_confidence": 0.15,
        }
        components = {k: round(v, 1) for k, v in components.items()}
        score = round(sum(components[k] * weights[k] for k in components), 1)
        campaigns.append(
            {
                "campaign_id": cid,
                "campaign": str(group.campaign.iloc[0]),
                "platform": platform,
                "metrics": now,
                "previous_metrics": before,
                "changes": deltas,
                "health_score": score,
                "components": {k: round(v, 1) for k, v in components.items()},
                "weights": weights,
                "targets": target,
                "issues": issues,
                "cvr_interval_95": wilson(now["conversions"], now["clicks"]),
                "complete_windows": complete,
                "quality_available": now["mql_rate"] is not None,
            }
        )
    return {
        "end_date": end,
        "window_days": window,
        "overview": metrics(recent),
        "platforms": [{"platform": p, **metrics(g)} for p, g in recent.groupby("platform")],
        "campaigns": campaigns,
        "fatigue": fatigue,
        "landing_pages": [p for cid, p in page_map.items() if cid in set(recent.campaign_id)],
        "confidence_note": "Wilson intervals describe observed CVR. Trend thresholds are exploratory, "
        "not causal significance tests; repeated users and multiple comparisons limit inference.",
    }
