import pytest

from src.core.scoring import score_strategy


def seg(trades, exp_r, pf, net=50.0, dd=10.0):
    return {"trades": trades, "expectancy_r": exp_r, "profit_factor": pf,
            "net_points": net, "max_drawdown_points": dd}


def split(all_n=120, oos_n=40, is_r=0.3, oos_r=0.3, oos_pf=1.9, net=50.0, dd=10.0):
    return {"all": seg(all_n, 0.3, 1.8, net, dd), "in_sample": seg(all_n - oos_n, is_r, 1.8),
            "out_of_sample": seg(oos_n, oos_r, oos_pf)}


def test_strong_robust_strategy_is_retained_for_paper_only():
    s = score_strategy(split())
    assert s["score"] == 10.0 and s["tier"] == "RETAINED" and s["eligible_for"] == "paper_trading"


def test_watch_band_is_orange_tier():
    s = score_strategy(split(oos_r=0.10, oos_pf=1.2, net=12.0, dd=10.0))
    assert 5.0 <= s["score"] < 6.0 and s["tier"] == "WATCH" and s["eligible_for"] is None


@pytest.mark.parametrize("kw,gate,cap", [
    ({"all_n": 25, "oos_n": 12}, "INSUFFICIENT_SAMPLE", 4.0),
    ({"oos_n": 5}, "INSUFFICIENT_OOS", 4.5),
    ({"oos_r": -0.1, "oos_pf": 0.8}, "OOS_NOT_PROFITABLE", 4.9),
])
def test_hard_gates_cap_score(kw, gate, cap):
    s = score_strategy(split(**kw))
    assert gate in s["gates"] and s["score"] <= cap and s["tier"] == "REJECTED"


def test_in_sample_only_success_is_rejected():
    s = score_strategy(split(is_r=0.6, oos_r=-0.05, oos_pf=0.9))
    assert s["tier"] == "REJECTED"


def test_synthetic_data_never_scores():
    s = score_strategy(split(), synthetic=True)
    assert s["score"] == 0.0 and "SYNTHETIC_DATA" in s["gates"]


def test_score_is_deterministic():
    assert score_strategy(split()) == score_strategy(split())
