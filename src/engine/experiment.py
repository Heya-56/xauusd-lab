from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json

@dataclass
class ExperimentResult:
    experiment: str
    mode: str
    status: str
    message: str
    timestamp_utc: str
    def to_json(self):
        return json.dumps(asdict(self), indent=2)

class Experiment:
    def __init__(self, config): self.config = config
    def run(self):
        exp=self.config["experiment"]; execution=self.config["execution"]
        return ExperimentResult(exp["name"], execution["mode"], "READY", "Research scaffold verified. No order was created. Candidate strategies and data adapters can now be plugged in.", datetime.now(timezone.utc).isoformat())
