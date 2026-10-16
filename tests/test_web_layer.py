"""The presentation layer must not contain signal or risk logic."""
import json
import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"
FORBIDDEN_JS = re.compile(r"\b(ema|sma|macd|rsi|atr|pivot\w*|evaluate_risk|backtest)\s*\(", re.I)


def test_js_has_no_indicator_or_risk_math():
    for js in (WEB / "js").glob("*.js"):
        assert not FORBIDDEN_JS.search(js.read_text()), js.name


def test_css_is_presentational_only():
    for css in (WEB / "styles").glob("*.css"):
        text = css.read_text().lower()
        assert "expression(" not in text and "javascript:" not in text


def test_demo_snapshot_is_labelled_synthetic_and_not_executable():
    snap = json.loads((WEB / "data" / "demo-snapshot.json").read_text())
    assert snap["snapshot_kind"] == "DEMO_SYNTHETIC_FIXTURE"
    assert snap["provenance"]["instrument_type"] == "synthetic_fixture"
    assert snap["latest_signal"]["execution_allowed"] is False


def test_demo_snapshot_is_reproducible():
    import sys
    sys.path.insert(0, str(WEB.parent))
    from research.build_dashboard_snapshot import build
    fresh = build()
    stored = json.loads((WEB / "data" / "demo-snapshot.json").read_text())
    assert fresh["latest_signal"]["data_hash"] == stored["latest_signal"]["data_hash"]
    assert fresh["recent_signals"] == stored["recent_signals"]
    assert fresh["performance"] == stored["performance"]
