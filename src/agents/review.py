"""Optional multi-agent review (TradingAgents-inspired roles, no framework copied).

Roles: technical analyst, structure analyst, bull reviewer, bear reviewer,
orchestrator. Each returns a schema-validated AgentOutput whose claims must cite
evidence IDs that exist in the SignalRecord. Nothing here can change the
decision, risk limits, or execution permission: the review is attached as
advisory metadata only. With no LLM configured (default), deterministic agents
produce the review; if an LLM adapter fails, times out or returns invalid
output, the review is marked rejected and the deterministic decision stands.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Protocol

from src.core.contracts import Decision, SignalRecord

ROLES = ("technical_analyst", "structure_analyst", "bull_reviewer", "bear_reviewer", "orchestrator")
STANCES = ("support", "oppose", "neutral")
STRUCTURE_KINDS = {"pivot", "level"}


@dataclass
class Claim:
    code: str
    evidence_ids: list[str]


@dataclass
class AgentOutput:
    role: str
    stance: str
    claims: list[Claim] = field(default_factory=list)
    rejection_reasons: list[str] = field(default_factory=list)


class LLMAdapter(Protocol):
    """Implement to plug a model. Must return raw dict outputs per role or raise."""
    name: str

    def review(self, record: dict, timeout_s: float) -> list[dict]: ...


def validate_output(raw: dict, record: SignalRecord) -> AgentOutput:
    """Reject anything malformed or citing evidence that does not exist."""
    allowed = {"role", "stance", "claims", "rejection_reasons"}
    if not isinstance(raw, dict) or set(raw) - allowed:
        raise ValueError("agent output has unexpected fields")
    if raw.get("role") not in ROLES or raw.get("stance") not in STANCES:
        raise ValueError("agent role/stance invalid")
    known = record.evidence_ids()
    claims = []
    for c in raw.get("claims", []):
        ids = c.get("evidence_ids") if isinstance(c, dict) else None
        if not isinstance(c.get("code"), str) or not ids or not isinstance(ids, list):
            raise ValueError("claim without evidence")
        unknown = [i for i in ids if i not in known]
        if unknown:
            raise ValueError(f"claim cites unknown evidence {unknown}")
        claims.append(Claim(c["code"], list(ids)))
    reasons = raw.get("rejection_reasons", [])
    if not isinstance(reasons, list) or not all(isinstance(r, str) for r in reasons):
        raise ValueError("rejection_reasons must be list[str]")
    return AgentOutput(raw["role"], raw["stance"], claims, reasons)


def deterministic_review(record: SignalRecord) -> list[dict]:
    ev = [(r, e) for r in record.strategy_results for e in r.evidence]
    tech = [e.evidence_id for _, e in ev if e.kind == "indicator"]
    struct = [e.evidence_id for _, e in ev if e.kind in STRUCTURE_KINDS]
    directional = [r for r in record.strategy_results if r.decision is not Decision.NO_TRADE]
    support = [e.evidence_id for r in directional for e in r.evidence]
    out = [
        {"role": "technical_analyst", "stance": "neutral",
         "claims": [{"code": "INDICATORS_COMPUTED", "evidence_ids": tech[:10]}] if tech else []},
        {"role": "structure_analyst", "stance": "neutral",
         "claims": [{"code": "STRUCTURE_LEVELS", "evidence_ids": struct[:10]}] if struct else []},
        {"role": "bull_reviewer", "stance": "support" if record.decision is Decision.BUY else "neutral",
         "claims": [{"code": f"{r.strategy_id}:{r.decision.value}", "evidence_ids": [e.evidence_id for e in r.evidence][:5]}
                    for r in directional if r.decision is Decision.BUY and r.evidence]},
        {"role": "bear_reviewer", "stance": "support" if record.decision is Decision.SELL else "oppose",
         "claims": [{"code": f"{r.strategy_id}:{r.decision.value}", "evidence_ids": [e.evidence_id for e in r.evidence][:5]}
                    for r in directional if r.decision is Decision.SELL and r.evidence],
         "rejection_reasons": list(record.risk.veto_codes) + [c for c in record.reason_codes
                                                              if c.startswith(("CONFLICT", "FILTER_BLOCK", "DATA:"))]},
        {"role": "orchestrator", "stance": "support" if record.decision is not Decision.NO_TRADE else "neutral",
         "claims": [{"code": f"FINAL:{record.decision.value}", "evidence_ids": support[:10]}] if support else [],
         "rejection_reasons": [] if record.decision is not Decision.NO_TRADE else ["NO_ELIGIBLE_SIGNAL"]},
    ]
    return out


def run_review(record: SignalRecord, llm: LLMAdapter | None = None, timeout_s: float = 10.0) -> dict:
    """Attach an advisory review. Never alters record.decision or record.risk."""
    source, raw = "deterministic", None
    if llm is not None:
        try:
            raw = llm.review(record.to_dict(), timeout_s)
            source = f"llm:{llm.name}"
        except Exception as exc:  # outage, timeout, quota -> deterministic fallback
            source = f"deterministic_fallback:{type(exc).__name__}"
            raw = None
    if raw is None:
        raw = deterministic_review(record)
    try:
        outputs = [validate_output(o, record) for o in raw]
        roles = {o.role for o in outputs}
        if roles != set(ROLES):
            raise ValueError(f"missing roles {sorted(set(ROLES) - roles)}")
        review = {"status": "accepted", "source": source, "advisory_only": True,
                  "outputs": [asdict(o) for o in outputs]}
    except ValueError as exc:
        review = {"status": "rejected", "source": source, "advisory_only": True,
                  "error": str(exc), "outputs": []}
    record.agent_review = review
    return review
