"""Repository-wide safety invariants."""
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_live_execution_constant_is_off():
    from src.core import risk_gate
    assert risk_gate.LIVE_EXECUTION_ENABLED is False


def test_configs_keep_live_disabled():
    for f in ("config/experiment.yml", "config/lab-v2.yml"):
        text = yaml.safe_load((ROOT / f).read_text())
        assert "live_orders_enabled: false" in yaml.safe_dump(text)
    for p in json.loads((ROOT / "config/profiles.json").read_text())["profiles"].values():
        assert p["mode"] in ("research", "paper")


def test_existing_ibkr_order_path_blocked_by_default(monkeypatch):
    monkeypatch.setenv("IBKR_CONID", "1")
    monkeypatch.delenv("XAUUSD_LIVE_ORDERS", raising=False)
    from src.execution.ibkr import IBKRExecution
    assert IBKRExecution().place("BUY", 1).status == "BLOCKED"


def test_no_price_hardcoded_in_engine():
    for py in (ROOT / "src").rglob("*.py"):
        assert "15000" not in py.read_text() and "15 000" not in py.read_text(), py


def test_no_obvious_secrets_committed():
    pat = re.compile(r"(sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN (RSA )?PRIVATE KEY)")
    for f in ROOT.rglob("*"):
        if f.is_file() and ".git" not in f.parts and f.suffix in {".py", ".json", ".yml", ".toml", ".js", ".md", ".sql"}:
            assert not pat.search(f.read_text(errors="ignore")), f
