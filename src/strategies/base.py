from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import Literal

Action = Literal["BUY", "SELL", "NONE"]


@dataclass
class Signal:
    action: Action
    entry: float
    stop_loss: float | None = None
    tp1: float | None = None
    tp2: float | None = None
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class StrategyCandidate(ABC):
    """Une stratégie lit des bougies clôturées et renvoie un Signal pour la dernière."""

    name = "candidate"
    warmup = 1        # nombre minimal de bougies avant de pouvoir signaler
    timeframe = 300   # unité de temps des bougies attendues, en secondes (300 = M5)

    @abstractmethod
    def evaluate(self, candles: list[dict]) -> Signal:
        raise NotImplementedError
