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
    import subprocess
    try:
        tracked = subprocess.check_output(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT, text=True).split()
        files = [ROOT / f for f in tracked]
    except Exception:
        files = [f for f in ROOT.rglob("*") if ".git" not in f.parts and "node_modules" not in f.parts]
    for f in files:
        if f.is_file() and f.suffix in {".py", ".json", ".yml", ".toml", ".js", ".md", ".sql", ".html"}:
            assert not pat.search(f.read_text(errors="ignore")), f


def test_mql5_scanner_cannot_trade():
    """Every Hinova EA is decision-support only: no trading API may appear in any MQL5 source."""
    forbidden = re.compile(r"\b(OrderSend|OrderSendAsync|CTrade|PositionOpen|PositionClose)\b|Trade\.mqh")
    files = list((ROOT / "mql5").rglob("*.mq5")) + list((ROOT / "mql5").rglob("*.mqh"))
    assert files, "scanner sources missing"
    for f in files:
        code = "\n".join(l for l in f.read_text(encoding="utf-8").splitlines() if not l.strip().startswith("//"))
        assert not forbidden.search(code), f


def test_bridge_ea_emits_every_contract_field():
    """The MQL5 bridge must write each key of the shared payload fixture (contract drift guard)."""
    fx = json.loads((ROOT / "mql5/HinovaBridge/payload.example.json").read_text())
    src = (ROOT / "mql5/HinovaBridge/HinovaBridge.mq5").read_text(encoding="utf-8-sig")
    keys = set(fx) | set(fx["provenance"]) | set(fx["account"]) | set(fx["candles"][0])
    missing = [k for k in keys if f'\\"{k}\\"' not in src]
    assert not missing, missing
    assert "CopyRates(_Symbol, InpTimeframe, 1," in src          # closed bars only
