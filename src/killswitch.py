"""Frein d'urgence (STOP). Un simple fichier partagé par tous les processus de la machine :
s'il existe, plus aucun agent ne calcule, le moteur papier ferme sa position et n'en ouvre plus,
et l'exécution broker refuse tout ordre. Il ne se relâche que par une action humaine explicite."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _path() -> Path:
    return Path(os.getenv("KILL_SWITCH_FILE", "KILL_SWITCH"))


def status() -> dict:
    p = _path()
    if not p.exists():
        return {"engaged": False}
    try:
        return {"engaged": True, **json.loads(p.read_text() or "{}")}
    except ValueError:
        return {"engaged": True, "reason": "fichier STOP présent"}


def engaged() -> bool:
    return _path().exists()


def engage(reason: str = "STOP manuel", by: str = "interface") -> dict:
    _path().write_text(json.dumps({"reason": reason[:200], "by": by[:60],
                                   "at": datetime.now(timezone.utc).isoformat()}))
    return status()


def release() -> dict:
    _path().unlink(missing_ok=True)
    return status()
