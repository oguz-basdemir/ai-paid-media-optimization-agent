"""Reproducible, explicitly synthetic daily creative-level fixtures."""

import json
import math
import random
from pathlib import Path

import pandas as pd

PLATFORMS = ("Google Ads", "Meta Ads", "LinkedIn Ads")
TARGETS = {
    "Google Ads": {"cpa": 75.0, "roas": 3.0, "cvr": 0.045, "mql_rate": 0.50},
    "Meta Ads": {"cpa": 90.0, "roas": 2.5, "cvr": 0.025, "mql_rate": 0.40},
    "LinkedIn Ads": {"cpa": 190.0, "roas": 1.8, "cvr": 0.040, "mql_rate": 0.65},
}


def generate(seed: int = 42, days: int = 84) -> tuple[pd.DataFrame, list[dict]]:
    rng = random.Random(seed)
    rows, pages = [], []
    start = pd.Timestamp("2026-06-01")
    scenarios = ["Healthy", "Creative fatigue", "Landing mismatch", "Tracking anomaly"]
    for pi, platform in enumerate(PLATFORMS):
        for si, scenario in enumerate(scenarios):
            cid = f"{['G', 'M', 'L'][pi]}{si + 1:02d}"
            url = f"https://demo.example/{cid.lower()}"
            pages.append(
                {
                    "landing_page": url,
                    "campaign_id": cid,
                    "ad_message": "Analytics software for revenue teams. Book a product demo.",
                    "keywords": ["analytics", "revenue", "demo"],
                    "proposition": "Enterprise payroll automation"
                    if si == 2
                    else "Revenue analytics software",
                    "headline": "Simplify payroll today" if si == 2 else "Analytics for revenue teams",
                    "cta": "Buy now" if si == 2 else "Book a demo",
                    "goal": "demo",
                    "synthetic": True,
                }
            )
            for day in range(days):
                late = max(0, (day - (days - 28)) / 27)
                for creative in range(2):
                    volume = (1600 + pi * 200) * (1 + 0.08 * math.sin(day / 7))
                    if si == 3:
                        volume *= 1 + 0.8 * late
                    impressions = max(1, int(volume * rng.uniform(0.80, 1.20)))
                    ctr = [0.065, 0.019, 0.012][pi] * rng.uniform(0.85, 1.15)
                    cpc = [2.3, 1.1, 5.0][pi] * rng.uniform(0.85, 1.15)
                    cvr = [0.065, 0.042, 0.065][pi]
                    freq = [1.25, 1.65, 1.4][pi] + rng.uniform(0, 0.4)
                    if si == 1:
                        ctr *= 1 - 0.55 * late
                        cpc *= 1 + 0.40 * late
                        freq += 4 * late
                    if si == 2:
                        cvr *= 0.27
                    if si == 3:
                        cvr *= 1 - 0.95 * late
                    clicks = min(impressions, max(0, int(impressions * ctr)))
                    conversions = sum(rng.random() < cvr for _ in range(clicks))
                    spend = round(clicks * cpc, 2)
                    leads = conversions
                    mqls = (
                        None
                        if pi == 0 and si == 0
                        else sum(rng.random() < [0.57, 0.46, 0.72][pi] for _ in range(leads))
                    )
                    revenue = round(conversions * [230, 120, 430][pi] * rng.uniform(0.8, 1.2), 2)
                    rows.append(
                        {
                            "date": (start + pd.Timedelta(days=day)).date().isoformat(),
                            "platform": platform,
                            "campaign_id": cid,
                            "campaign": f"{platform.split()[0]} | Revenue Analytics | {scenario}",
                            "ad_group": f"{cid} - Decision makers",
                            "creative": f"{cid}-creative-{creative + 1}",
                            "audience": [
                                "High-intent search",
                                "Marketing leaders",
                                "Revenue operations leaders",
                            ][pi],
                            "impressions": impressions,
                            "clicks": clicks,
                            "ctr": clicks / impressions,
                            "cpc": spend / clicks if clicks else None,
                            "spend": spend,
                            "conversions": conversions,
                            "cvr": conversions / clicks if clicks else None,
                            "cpa": spend / conversions if conversions else None,
                            "revenue": revenue,
                            "roas": revenue / spend if spend else None,
                            "leads": leads,
                            "mqls": mqls,
                            "frequency": round(freq, 3),
                            "landing_page": url,
                            "scenario": scenario,
                            "synthetic": True,
                        }
                    )
    return pd.DataFrame(rows), pages


def write_samples(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    frame, pages = generate()
    frame.to_csv(directory / "paid_media.csv", index=False)
    (directory / "landing_pages.json").write_text(json.dumps(pages, indent=2), encoding="utf-8")
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "synthetic": True,
                "seed": 42,
                "days": 84,
                "rows": len(frame),
                "grain": "date × platform × campaign × ad group × creative × audience × landing page",
                "currency": "USD",
                "conversion": "synthetic demo lead",
                "attribution": "mock 7-day click",
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    write_samples(Path(__file__).resolve().parents[1] / "data")
