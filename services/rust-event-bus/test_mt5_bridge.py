import unittest
from types import SimpleNamespace
from mt5_bridge import normalize_tick

class NormalizeTickTests(unittest.TestCase):
    def test_normalizes_quote_and_does_not_claim_spot(self):
        t=SimpleNamespace(time_msc=1790000000123,bid=2300.1,ask=2300.3)
        r=normalize_tick(t,symbol="XAUUSD",venue="Broker-Demo",sequence=7)
        self.assertEqual(r["source"],"mt5")
        self.assertEqual(r["instrument_type"],"broker_instrument_unverified")
        self.assertEqual(r["timestamp_ms"],1790000000123)
        self.assertEqual((r["bid"],r["ask"]),(2300.1,2300.3))
    def test_rejects_crossed_quote(self):
        with self.assertRaises(ValueError):
            normalize_tick(SimpleNamespace(time_msc=1,bid=2,ask=1),symbol="XAUUSD",venue="",sequence=1)
    def test_rejects_missing_quote(self):
        with self.assertRaises(ValueError):
            normalize_tick(SimpleNamespace(time_msc=0,bid=0,ask=0),symbol="XAUUSD",venue="",sequence=1)
if __name__=="__main__": unittest.main()
