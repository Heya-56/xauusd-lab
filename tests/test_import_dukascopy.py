import json

import pytest

from research.import_dukascopy import ImportError_, convert
from src.core.contracts import InstrumentType
from src.data.adapters import CsvFileAdapter
from src.data.ohlc import validate_series


def _raw(tmp_path, lines):
    p = tmp_path / "raw.csv"
    p.write_text("timestamp,open,high,low,close,volume\n" + "\n".join(lines) + "\n")
    return p


def test_convert_ms_timestamps_and_provenance(tmp_path):
    raw = _raw(tmp_path, ["1767225600000,2400.1,2401.5,2399.8,2401.2,12.5",
                          "1767226500000,2401.2,2402.0,2400.9,2401.7,9.0"])
    dst = tmp_path / "out" / "x.csv"
    assert convert(raw, dst, "M15") == 2
    meta = json.loads((tmp_path / "out" / "x.csv.meta.json").read_text())
    assert meta["instrument_type"] == "cfd" and meta["source"] == "dukascopy:xauusd:bid"
    s = CsvFileAdapter(dst).load()
    assert s.provenance.instrument_type is InstrumentType.CFD
    assert s.candles[0].ts == 1767225600 and validate_series(s, expected_symbol="XAUUSD").ok


@pytest.mark.parametrize("line", ["1767225600000,abc,1,1,1,0", "1767225601000,1,1,1,1,0"])
def test_malformed_or_misaligned_rows_abort(tmp_path, line):
    with pytest.raises(ImportError_):
        convert(_raw(tmp_path, [line]), tmp_path / "x.csv", "M15")


def test_wrong_columns_rejected(tmp_path):
    p = tmp_path / "raw.csv"
    p.write_text("date,price\n2026-01-01,2400\n")
    with pytest.raises(ImportError_):
        convert(p, tmp_path / "x.csv", "M15")


def test_spread_from_ask_and_misalignment(tmp_path):
    bid = _raw(tmp_path, ["1767225600000,2400.1,2401.5,2399.8,2401.2,1"])
    ask = tmp_path / "ask.csv"
    ask.write_text("timestamp,open,high,low,close,volume\n1767225600000,2400.4,2401.8,2400.1,2401.5,1\n")
    dst = tmp_path / "x.csv"
    convert(bid, dst, "M15", ask_src=ask)
    s = CsvFileAdapter(dst).load()
    assert s.candles[0].spread == pytest.approx(0.3)
    ask.write_text("timestamp,open,high,low,close,volume\n1767226500000,1,1,1,1,1\n")
    with pytest.raises(ImportError_, match="missing candle"):
        convert(bid, dst, "M15", ask_src=ask)
