"""Python mirror of mql5/HinovaGoldScanner/HGS_Scanner.mqh (same rules, same order).

Used to test the scanner's LOGIC on simulated quote streams, since MQL5 cannot be
compiled or run in CI. Any change to HGS_Scanner.mqh must be mirrored here.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

NEUTRAL, BUY, SELL = 0, 1, 2


@dataclass
class Tick:
    time_msc: int
    bid: float
    ask: float


class SpreadScanner:
    def __init__(self, *, point=0.01, mode="z", window=600, sample_ms=1000, max_quote_age_ms=5000,
                 z_entry=2.0, z_exit=0.5, pts_entry=150.0, pts_exit=50.0,
                 min_dev_pts=50.0, cost_mult=3.0, confirm_samples=3):
        if window < 30 or sample_ms < 100 or max_quote_age_ms < 500:
            raise ValueError("bad params")
        if not (0 <= z_exit < z_entry) or not (0 <= pts_exit < pts_entry):
            raise ValueError("exit must be < entry")
        if confirm_samples < 1 or min_dev_pts < 0 or cost_mult < 0:
            raise ValueError("bad gate params")
        self.min_dev_pts, self.cost_mult, self.confirm = min_dev_pts, cost_mult, confirm_samples
        self.buy_streak = self.sell_streak = 0
        self.point, self.mode, self.window = point, mode, window
        self.sample_ms, self.max_age = sample_ms, max_quote_age_ms
        self.z_entry, self.z_exit, self.pts_entry, self.pts_exit = z_entry, z_exit, pts_entry, pts_exit
        self.buf = [0.0] * window
        self.head = self.count = 0
        self.sum = self.sumsq = 0.0
        self.last_sample = 0
        self.state = NEUTRAL
        self.prev_published = NEUTRAL
        self.changed = False
        self.snap = {"status": "INIT", "signal": NEUTRAL, "ready": False, "zscore": 0.0}

    def _push(self, v):
        if self.count == self.window:
            old = self.buf[self.head]
            self.sum -= old
            self.sumsq -= old * old
        else:
            self.count += 1
        self.buf[self.head] = v
        self.sum += v
        self.sumsq += v * v
        self.head = (self.head + 1) % self.window

    def _next(self, m, exit_):
        """Entries need a confirmed streak (computed on samples); exits are immediate."""
        buy_ok, sell_ok = self.buy_streak >= self.confirm, self.sell_streak >= self.confirm
        if self.state == NEUTRAL:
            return BUY if buy_ok else SELL if sell_ok else NEUTRAL
        if self.state == BUY:
            return SELL if sell_ok else NEUTRAL if m >= -exit_ else BUY
        return BUY if buy_ok else NEUTRAL if m <= exit_ else SELL

    def _publish(self, s, status, ready):
        self.state = s
        self.snap.update(signal=s, status=status, ready=ready)
        if s != self.prev_published:
            self.changed = True

    def evaluate(self, ts: Tick | None, tr: Tick | None):
        if ts is None or tr is None:
            return self._publish(NEUTRAL, "NO_TICK", False)
        self.snap.update(time_msc=ts.time_msc, spread_pts=round((ts.ask - ts.bid) / self.point))
        if ts.bid <= 0 or ts.ask < ts.bid or tr.bid <= 0 or tr.ask < tr.bid:
            return self._publish(NEUTRAL, "BAD_QUOTE", False)
        diff = (ts.bid + ts.ask) / 2 - (tr.bid + tr.ask) / 2
        self.snap["diff"] = diff
        if abs(ts.time_msc - tr.time_msc) > self.max_age:
            return self._publish(NEUTRAL, "STALE_REF", False)
        now = max(ts.time_msc, tr.time_msc)
        sampled = False
        if now - self.last_sample >= self.sample_ms:
            self._push(diff)
            self.last_sample = now
            sampled = True
        if self.count < self.window:
            return self._publish(NEUTRAL, "WARMUP", False)
        mean = self.sum / self.count
        sd = math.sqrt(max(self.sumsq / self.count - mean * mean, 0.0))
        dev = diff - mean
        z = dev / sd if sd > 0 else 0.0
        self.snap.update(mean=mean, stdev=sd, deviation_pts=dev / self.point, zscore=z)
        if sd <= 0:
            return self._publish(NEUTRAL, "FLAT", False)
        m, e, x = (z, self.z_entry, self.z_exit) if self.mode == "z" else (dev / self.point, self.pts_entry, self.pts_exit)
        if sampled:  # streaks advance once per sample, never per tick
            min_pts = max(self.min_dev_pts, self.cost_mult * self.snap["spread_pts"])
            big = abs(dev / self.point) >= min_pts
            self.buy_streak = self.buy_streak + 1 if (m <= -e and big) else 0
            self.sell_streak = self.sell_streak + 1 if (m >= e and big) else 0
        self._publish(self._next(m, x), "OK", True)

    def consume_change(self):
        if not self.changed:
            return None
        frm, to = self.prev_published, self.snap["signal"]
        self.prev_published, self.changed = to, False
        return frm, to
