"""Hard AI usage limits. Deterministic code never consumes this budget.

The guard is checked BEFORE any model call. When AI is disabled, the task is
not allowed, or a daily cap would be exceeded, the call is refused and the
caller falls back to deterministic output. Every refusal and every allowed
call is recorded in the ledger so the bill can be audited.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

POLICY_PATH = Path(__file__).resolve().parents[2] / "config" / "ai_policy.json"


def load_policy(path: Path = POLICY_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class AIBudget:
    policy: dict
    ledger: list[dict] = field(default_factory=list)

    def _today(self, now: int) -> str:
        return datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%d")

    def _used(self, day: str) -> tuple[int, int]:
        rows = [r for r in self.ledger if r["day"] == day and r["status"] == "allowed"]
        return len(rows), sum(r["tokens"] for r in rows)

    def authorize(self, task: str, input_tokens: int, now: int) -> int:
        """Return the max output tokens allowed, or raise BudgetExceeded."""
        p, day = self.policy, self._today(now)
        reason = None
        if not p.get("enabled"):
            reason = "AI_DISABLED"
        elif task not in p["allowed_tasks"]:
            reason = f"TASK_NOT_ALLOWED:{task}"
        elif input_tokens > p["max_input_tokens_per_call"]:
            reason = "INPUT_TOO_LARGE"
        else:
            calls, tokens = self._used(day)
            worst = input_tokens + p["max_output_tokens_per_call"]
            if calls >= p["max_calls_per_day"]:
                reason = "DAILY_CALLS_EXHAUSTED"
            elif tokens + worst > p["max_tokens_per_day"]:
                reason = "DAILY_TOKENS_EXHAUSTED"
        if reason:
            self.ledger.append({"day": day, "task": task, "status": "refused", "reason": reason, "tokens": 0})
            raise BudgetExceeded(reason)
        self.ledger.append({"day": day, "task": task, "status": "allowed", "reason": None,
                            "tokens": input_tokens + p["max_output_tokens_per_call"]})
        return p["max_output_tokens_per_call"]

    def usage(self, now: int) -> dict:
        calls, tokens = self._used(self._today(now))
        return {"calls_today": calls, "tokens_reserved_today": tokens,
                "max_calls_per_day": self.policy["max_calls_per_day"],
                "max_tokens_per_day": self.policy["max_tokens_per_day"]}
