"""Strategy registry, profiles and server-side configuration validation.

The dashboard sends a *configuration* (which strategies are on, parameters,
profile). It never sends code. This module is the single place that turns an
untrusted configuration into a validated, hashed snapshot.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.core.contracts import TIMEFRAME_SECONDS, Mode, content_hash
from src.core.strategies import BUILTIN_STRATEGIES
from src.core.strategies.base import Strategy

PROFILES_PATH = Path(__file__).resolve().parents[2] / "config" / "profiles.json"

# Hard server-side ceilings. A profile or user config can only be stricter.
RISK_CEILINGS = {"max_risk_per_trade_pct": 1.0, "max_open_positions": 3, "max_daily_loss_pct": 3.0}


class ConfigError(ValueError):
    pass


class StrategyRegistry:
    def __init__(self, classes=BUILTIN_STRATEGIES):
        self._classes: dict[str, type[Strategy]] = {}
        for cls in classes:
            self.register(cls)

    def register(self, cls: type[Strategy]) -> None:
        if cls.strategy_id in self._classes:
            raise ValueError(f"duplicate strategy_id {cls.strategy_id}")
        self._classes[cls.strategy_id] = cls

    def ids(self) -> list[str]:
        return list(self._classes)

    def get(self, strategy_id: str) -> type[Strategy]:
        try:
            return self._classes[strategy_id]
        except KeyError:
            raise ConfigError(f"unknown strategy {strategy_id!r}") from None

    def catalog(self) -> list[dict]:
        return [c.describe() for c in self._classes.values()]


def load_profiles(path: Path = PROFILES_PATH) -> dict:
    profiles = json.loads(path.read_text(encoding="utf-8"))["profiles"]
    for name, p in profiles.items():
        _validate_profile(name, p)
    return profiles


def _validate_profile(name: str, p: dict) -> None:
    for tf in list(p["timeframes"].values()) + [p["decision_timeframe"]]:
        if tf not in TIMEFRAME_SECONDS:
            raise ConfigError(f"profile {name}: unknown timeframe {tf}")
    if p["mode"] not in (Mode.RESEARCH.value, Mode.PAPER.value):
        raise ConfigError(f"profile {name}: mode {p['mode']!r} not permitted")
    for k, ceiling in RISK_CEILINGS.items():
        if not (0 < p["risk"][k] <= ceiling):
            raise ConfigError(f"profile {name}: risk.{k} outside (0, {ceiling}]")


@dataclass(frozen=True)
class ValidatedConfig:
    profile_name: str
    profile: dict
    strategies: dict          # strategy_id -> validated params (enabled only)
    disabled: tuple[str, ...]
    config_hash: str

    def instantiate(self, registry: StrategyRegistry) -> list[Strategy]:
        return [registry.get(sid)(**params) for sid, params in self.strategies.items()]

    def to_dict(self) -> dict:
        return {"profile": self.profile_name, "strategies": self.strategies,
                "disabled": list(self.disabled), "config_hash": self.config_hash}


def validate_config(raw: dict, registry: StrategyRegistry, profiles: dict | None = None) -> ValidatedConfig:
    """Validate an untrusted dashboard/API configuration. Raises ConfigError."""
    if not isinstance(raw, dict):
        raise ConfigError("config must be an object")
    allowed_keys = {"profile", "strategies"}
    if set(raw) - allowed_keys:
        raise ConfigError(f"unknown config keys {sorted(set(raw) - allowed_keys)}")
    profiles = profiles if profiles is not None else load_profiles()
    pname = raw.get("profile")
    if pname not in profiles:
        raise ConfigError(f"unknown profile {pname!r}")
    profile = profiles[pname]
    enabled, disabled = {}, []
    for sid, entry in (raw.get("strategies") or {}).items():
        cls = registry.get(sid)
        if not isinstance(entry, dict) or set(entry) - {"enabled", "params"}:
            raise ConfigError(f"{sid}: entry must be {{enabled, params}}")
        if entry.get("enabled") is not True:
            disabled.append(sid)
            continue
        if not cls.available:
            raise ConfigError(f"{sid}: unavailable ({cls.unavailable_reason})")
        if sid not in profile["eligible_strategies"]:
            raise ConfigError(f"{sid}: not eligible for profile {pname}")
        try:
            enabled[sid] = cls.validate_params(entry.get("params") or {})
        except ValueError as exc:
            raise ConfigError(str(exc)) from exc
    h = content_hash({"profile": pname, "p": profile, "s": enabled})[:24]
    return ValidatedConfig(pname, profile, enabled, tuple(sorted(disabled)), h)
