from src.agents.review import run_review, validate_output
from src.core.contracts import Decision
from src.core.engine import evaluate
from src.core.risk_gate import AccountState

from conftest import cfg

import pytest

OK = AccountState(current_spread=0.3)


def _signal_record(series, registry):
    config = cfg(registry, "sr_breakout")
    for i in range(100, len(series)):
        rec = evaluate(series.upto(i), config, registry, account=OK, allow_synthetic=True)
        if rec.decision is not Decision.NO_TRADE:
            return rec
    raise AssertionError


def test_deterministic_review_without_any_llm(series, registry):
    rec = _signal_record(series, registry)
    before = rec.to_dict()
    review = run_review(rec)
    assert review["status"] == "accepted" and review["source"] == "deterministic"
    assert {o["role"] for o in review["outputs"]} == {"technical_analyst", "structure_analyst",
                                                      "bull_reviewer", "bear_reviewer", "orchestrator"}
    after = rec.to_dict()
    assert after["decision"] == before["decision"] and after["veto_codes"] == before["veto_codes"]


def test_fabricated_evidence_is_rejected(series, registry):
    rec = _signal_record(series, registry)
    with pytest.raises(ValueError, match="unknown evidence"):
        validate_output({"role": "bull_reviewer", "stance": "support",
                         "claims": [{"code": "RSI_IS_12", "evidence_ids": ["deadbeefdeadbeef"]}]}, rec)
    with pytest.raises(ValueError):
        validate_output({"role": "orchestrator", "stance": "support", "execution_allowed": True}, rec)
    with pytest.raises(ValueError, match="claim without evidence"):
        validate_output({"role": "bull_reviewer", "stance": "support", "claims": [{"code": "TRUST_ME"}]}, rec)


class _Down:
    name = "down"
    def review(self, record, timeout_s):
        raise TimeoutError("provider outage")


class _Liar:
    name = "liar"
    def review(self, record, timeout_s):
        return [{"role": r, "stance": "support", "claims": [{"code": "PRICE=9999", "evidence_ids": ["fake0000fake0000"]}]}
                for r in ("technical_analyst", "structure_analyst", "bull_reviewer", "bear_reviewer", "orchestrator")]


def _enabled_budget(**over):
    from src.agents.budget import AIBudget, load_policy
    return AIBudget(load_policy() | {"enabled": True} | over)


class _Counting:
    name = "counting"
    calls = 0
    def review(self, record, timeout_s):
        _Counting.calls += 1
        raise AssertionError("must not be called")


def test_ai_is_off_by_default_and_never_called(series, registry):
    rec = _signal_record(series, registry)
    review = run_review(rec, _Counting())
    assert _Counting.calls == 0 and review["source"] == "deterministic_budget:AI_DISABLED"
    assert review["status"] == "accepted"


def test_llm_outage_falls_back_and_liar_is_rejected(series, registry):
    rec = _signal_record(series, registry)
    decision = rec.decision
    assert run_review(rec, _Down(), budget=_enabled_budget()).get("source", "").startswith(
        "deterministic_fallback:TimeoutError")
    review = run_review(rec, _Liar(), budget=_enabled_budget())
    assert review["status"] == "rejected" and rec.decision is decision


def test_budget_caps_calls_and_tokens(series, registry):
    from src.agents.budget import BudgetExceeded
    b = _enabled_budget(max_calls_per_day=2)
    now = 1_800_000_000
    b.authorize("review_signal", 100, now)
    b.authorize("review_signal", 100, now)
    with pytest.raises(BudgetExceeded, match="DAILY_CALLS_EXHAUSTED"):
        b.authorize("review_signal", 100, now)
    with pytest.raises(BudgetExceeded, match="TASK_NOT_ALLOWED"):
        _enabled_budget().authorize("compute_indicators", 10, now)
    with pytest.raises(BudgetExceeded, match="DAILY_TOKENS_EXHAUSTED"):
        _enabled_budget(max_tokens_per_day=500).authorize("review_signal", 100, now)
    assert any(r["status"] == "refused" for r in b.ledger)


def test_proof_decision_identical_with_and_without_ai(series, registry):
    """Zero-hallucination proof: for every bar, the decision record (without the
    advisory review) is identical whether AI review runs, fails or lies."""
    from conftest import cfg
    config = cfg(registry, "macd_cross", "rsi_reversion", "sr_breakout", "atr_regime")
    for i in range(100, len(series), 7):
        base = evaluate(series.upto(i), config, registry, account=OK, allow_synthetic=True)
        for llm in (None, _Down(), _Liar()):
            rec = evaluate(series.upto(i), config, registry, account=OK, allow_synthetic=True)
            run_review(rec, llm, budget=_enabled_budget())
            a, b = base.to_dict(), rec.to_dict()
            a.pop("agent_review"); b.pop("agent_review")
            assert a == b
