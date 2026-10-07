from pathlib import Path
import yaml
from src.engine.experiment import Experiment

def main():
    config = yaml.safe_load(Path("config/experiment.yml").read_text())
    print(Experiment(config).run().to_json())

if __name__ == "__main__":
    main()
