"""Generate the experiment map for S.A.T.A. inside XAUUSD Lab."""
from __future__ import annotations
import csv
import json
from pathlib import Path
from src.strategies.sata_adapter import catalog

def build() -> list[dict]:
    rows = []
    for item in catalog():
        rows.append({
            **item,
            "status": "candidate",
            "trades": None,
            "profit_factor": None,
            "expectancy_r": None,
            "max_drawdown_pct": None,
            "oos": "pending",
            "paper": "pending",
        })
    return rows

def main() -> None:
    out = Path("artifacts")
    out.mkdir(exist_ok=True)
    rows = build()
    (out / "sata-cartography.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    with (out / "sata-cartography.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({
        "candidates": len(rows),
        "horizons": sorted({r["horizon"] for r in rows}),
        "methods": sorted({r["method"] for r in rows}),
        "winner_selected": False,
    }, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
