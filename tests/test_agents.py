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


def test_llm_outage_falls_back_and_liar_is_rejected(series, registry):
    rec = _signal_record(series, registry)
    decision = rec.decision
    assert run_review(rec, _Down())["source"].startswith("deterministic_fallback:TimeoutError")
    review = run_review(rec, _Liar())
    assert review["status"] == "rejected" and rec.decision is decision
