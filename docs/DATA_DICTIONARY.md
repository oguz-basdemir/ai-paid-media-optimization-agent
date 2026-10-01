# Synthetic data dictionary

Source: `data/paid_media.csv`, generated with seed 42. Dates June 1–August 23, 2026. 84 days × 12 campaigns × 2 creatives = 2,016 rows. `data/manifest.json` records provenance. No real accounts, products, customers or landing pages are used.

| Field | Type / units | Meaning |
|---|---|---|
| date | ISO date | Observation day |
| platform | string | Google Ads, Meta Ads or LinkedIn Ads |
| campaign_id | string | Stable G/M/L campaign identifier |
| campaign | string | Display name with fixture scenario |
| ad_group | string | Synthetic ad group / ad set grouping |
| creative | string | Stable creative identifier within campaign |
| audience | string | Mock targeting persona |
| impressions | integer | Served ad impressions |
| clicks | integer | Clicks, bounded by impressions |
| ctr | fraction | Clicks / impressions |
| cpc | USD / click, nullable | Spend / clicks |
| spend | USD | Synthetic delivered spend |
| conversions | integer | Mock attributed demo leads |
| cvr | fraction, nullable | Conversions / clicks |
| cpa | USD / conversion, nullable | Spend / conversions |
| revenue | USD | Mock attributed pipeline value, not cash revenue |
| roas | multiple, nullable | Revenue / spend |
| leads | integer | Same demo event as conversions in this fixture |
| mqls | nullable count | Qualified leads where mock CRM coverage exists |
| frequency | decimal | Mock rolling exposure proxy, not unique reach |
| landing_page | reserved URL | Non-live `.example` page key |
| scenario | string | Fixture provenance only; not used by scoring/detection |
| synthetic | boolean | Explicit fixture marker |

Row ratios are conveniences for inspection; aggregate metrics always recompute numerator and denominator totals. Empty CSV values represent unknowns, including undefined CPA with zero conversions. MQLs are intentionally unknown for G01 to demonstrate coverage handling. CPL equals CPA in this lead-generation scenario; separate event definitions would be needed for another funnel.

`landing_pages.json` contains campaign ID, page key, ad promise, keyword tokens, headline, proposition, CTA, goal and a synthetic marker. Mismatch scenarios deliberately use payroll copy for an analytics ad. Pages are never fetched.

The last 28 days introduce progressive creative fatigue and tracking loss; campaign volumes and daily metrics include seeded variation. Counts are bounded and metrics internally consistent. Attribution delays and user-level exposure are not simulated.
