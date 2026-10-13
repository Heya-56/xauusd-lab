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
