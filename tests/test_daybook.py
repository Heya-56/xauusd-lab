from datetime import datetime, timedelta, timezone

from src import daybook
from src.engine.manual_paper import ManualPaperBook
from src.journal import Journal


def test_journal_day_and_night(tmp_path):
    b = ManualPaperBook(Journal(str(tmp_path / "j.db")))
    b.on_tick(4000.0, 4000.2, "2026-10-27T23:50:00")
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    b.open("BUY", 0.02, sl=3950, tp1=4030, tp2=4060, exit_at=past)        # nuit : fermée à l'heure fixe
    b.open("SELL", 0.01, sl=4010, tp1=3990, tp2=3980)                      # manuel : fermé au SL
    b.on_tick(4011.0, 4011.2, "2026-10-28T10:00:00")
    j = daybook.build(b.j)
    assert j["day"] == "2026-10-28" and j["summary"]["trades"] == 2
    kinds = {t["strategy"]: t for t in j["trades"]}
    assert kinds["Fenêtre nuit"]["reason"] == "Fermeture auto (nuit)" and kinds["Fenêtre nuit"]["pnl"] > 0
    assert kinds["Manuel"]["reason"] == "Stop touché" and kinds["Manuel"]["pnl"] < 0
    assert j["night"]["trades"] == 1
    csv = daybook.to_csv(b.j)
    assert csv.splitlines()[0].startswith("opened_at;") and len(csv.splitlines()) == 3
