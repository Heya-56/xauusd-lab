import yaml
from src.engine.experiment import Experiment


def test_experiment_is_research_only():
    with open("config/experiment.yml", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    result = Experiment(config).run()
    assert result.status == "READY"
    assert "No order was created" in result.message
    assert config["execution"]["mode"] == "paper"
    assert config["execution"]["live_orders_enabled"] is False


def test_ibkr_backtest_indicators_are_deterministic():
    from research.ibkr_spot_backtest import ema, atr

    assert ema([1.0, 2.0, 3.0], 2) == [1.0, 1.6666666666666665, 2.5555555555555554]
    rows = [
        {"high": 2.0, "low": 1.0, "close": 1.5},
        {"high": 3.0, "low": 1.5, "close": 2.5},
    ]
    assert atr(rows, 2)[1] == 1.25
