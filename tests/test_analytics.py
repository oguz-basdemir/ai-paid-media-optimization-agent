import math

import pandas as pd
import pytest

from paid_media.analytics import change, diagnose, landing_alignment, metrics, wilson, windows
from paid_media.data import generate
from paid_media.experiments import recommendations, sample_size, simulate


def test_synthetic_fixture_reproducible_and_consistent(dataset):
    f, pages = dataset
    again, _ = generate()
    pd.testing.assert_frame_equal(f, again)
    assert len(f) == 2016 and f.campaign_id.nunique() == 12 and len(pages) == 12
    assert set(f.platform) == {"Google Ads", "Meta Ads", "LinkedIn Ads"}
    assert f.synthetic.all() and (f.clicks <= f.impressions).all()
    assert (f.conversions <= f.clicks).all()
    assert (f[f.mqls.notna()].mqls <= f[f.mqls.notna()].leads).all()
    assert ((f.ctr - f.clicks / f.impressions).abs() < 1e-9).all()


def test_metrics_ratio_of_sums_not_average_of_ratios(dataset):
    f, _ = dataset
    subset = f.iloc[:8]
    m = metrics(subset)
    assert m["ctr"] == pytest.approx(subset.clicks.sum() / subset.impressions.sum())
    assert m["cpa"] == pytest.approx(subset.spend.sum() / subset.conversions.sum())
    assert m["cpm"] == pytest.approx(subset.spend.sum() * 1000 / subset.impressions.sum())


def test_zero_denominators_are_unknown(dataset):
    f, _ = dataset
    empty = metrics(f.iloc[:0])
    assert all(empty[k] is None for k in ["ctr", "cpc", "cpa", "cvr", "roas", "cost_per_mql"])
    assert change(0, 0) is None
    assert wilson(0, 0) == [None, None]
    low, high = wilson(0, 100)
    assert low == pytest.approx(0) and 0 < high < 0.04


def test_mql_coverage_does_not_impute_unknown_as_zero(dataset):
    f, _ = dataset
    subset = f.iloc[:4].copy()
    subset["mqls"] = [None, 2, None, 3]
    m = metrics(subset)
    assert m["mqls"] == 5
    assert m["cost_per_mql"] == pytest.approx(subset.iloc[[1, 3]].spend.sum() / 5)
    assert 0 < m["mql_spend_coverage"] < 1


def test_nonoverlapping_equal_windows(dataset):
    f, _ = dataset
    recent, previous = windows(f, f.date.max())
    assert recent.date.nunique() == previous.date.nunique() == 14
    assert set(recent.date).isdisjoint(previous.date)


def test_scenario_detection_and_health_explanation(report):
    campaigns = {c["campaign_id"]: c for c in report["campaigns"]}
    assert "creative_fatigue" in {i["code"] for i in campaigns["M02"]["issues"]}
    assert "landing_mismatch" in {i["code"] for i in campaigns["G03"]["issues"]}
    assert "spend_without_results" in {i["code"] for i in campaigns["G04"]["issues"]}
    assert campaigns["M01"]["health_score"] > campaigns["M04"]["health_score"]
    for c in campaigns.values():
        assert 0 <= c["health_score"] <= 100
        assert c["health_score"] == pytest.approx(
            round(sum(c["components"][k] * c["weights"][k] for k in c["components"]), 1), abs=0.1
        )
    assert not campaigns["G01"]["quality_available"]


def test_low_volume_and_incomplete_trends_suppressed(dataset):
    f, pages = dataset
    partial = diagnose(f, pages, end=f.date.min())
    assert not partial["fatigue"]
    for c in partial["campaigns"]:
        assert not c["complete_windows"]
        assert "cpa_rising" not in {i["code"] for i in c["issues"]}
    thin = f[f.campaign_id == "G02"].copy()
    thin["clicks"] = 0
    thin["conversions"] = 0
    r = diagnose(thin, pages)
    assert "cpa_rising" not in {i["code"] for i in r["campaigns"][0]["issues"]}


def test_landing_metadata_alignment(dataset):
    _, pages = dataset
    healthy, mismatch = landing_alignment(pages[0]), landing_alignment(pages[2])
    assert healthy["alignment_score"] > mismatch["alignment_score"]
    assert not mismatch["cta_matches_goal"]


def test_every_issue_has_reproducible_experiment(report):
    records = recommendations(report)
    assert records == recommendations(report)
    assert len({r["id"] for r in records}) == len(records)
    for c in report["campaigns"]:
        for issue in c["issues"]:
            assert any(r["campaign_id"] == c["campaign_id"] and r["issue"] == issue["code"] for r in records)
    for r in records:
        assert r["status"] == "Proposed" and r["requires_human_approval"]
        assert all(
            r["experiment"][k]
            for k in ["hypothesis", "test", "primary_kpi", "secondary_kpi", "success_criteria"]
        )


def test_sample_planning_scales_with_mde():
    assert sample_size(0.04, 0.10) > sample_size(0.04, 0.20) > 0
    assert 17000 < sample_size(0.04, 0.15) < 19000
    with pytest.raises(ValueError):
        sample_size(0)


@pytest.mark.parametrize("fraction", [0, 0.1, 0.3])
def test_budget_conservation_caps_and_no_mutation(report, fraction):
    import copy

    before = copy.deepcopy(report)
    sim = simulate(report, fraction)
    assert sim["label"] == "Decision-support simulation - not financial forecasting."
    rows = pd.DataFrame(sim["rows"])
    for _, g in rows.groupby("platform"):
        assert g.simulated_spend.sum() == pytest.approx(g.historical_spend.sum())
    assert (rows.simulated_spend >= 0).all()
    assert (rows.budget_delta <= rows.historical_spend * 0.20 + 1e-8).all()
    assert (rows.budget_delta >= -rows.historical_spend * fraction - 1e-8).all()
    assert math.isclose(rows.budget_delta.sum(), 0, abs_tol=1e-8)
    assert report == before


def test_budget_invalid_shift_and_sparse_eligibility(report, dataset):
    with pytest.raises(ValueError):
        simulate(report, 0.5)
    f, p = dataset
    sparse = diagnose(f, p, end=f.date.min())
    assert all(r["budget_delta"] == 0 for r in simulate(sparse)["rows"])
