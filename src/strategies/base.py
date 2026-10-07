from abc import ABC, abstractmethod

class StrategyCandidate(ABC):
    name = "candidate"
    @abstractmethod
    def evaluate(self, candles):
        raise NotImplementedError
