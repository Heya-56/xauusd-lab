# Third-party notices

## profitable-expert-advisor (MIT)

`src/core/strategies/ema_slope_distance.py` re-implements, in Python and from scratch, the trading
idea of `EMASlopeDistanceCocktailXAUUSD` from https://github.com/zhutoutoutousan/profitable-expert-advisor
(commit 982c3ad, 2026-07-02). No source code was copied. Notice reproduced as a courtesy:

```
MIT License

Copyright (c) 2026 Profitable Expert Advisor contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

Audit notes on the original (why figures published there are not trusted here): it reads the
forming bar (`iClose(..., 0)`), opens positions with no stop-loss, and uses genetically optimised
parameters without a documented out-of-sample period.

## dukascopy-node (MIT)

Used only as an external CLI (`npx dukascopy-node@1.50.0`); not vendored.
