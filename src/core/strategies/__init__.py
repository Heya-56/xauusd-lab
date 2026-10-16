from src.core.strategies.atr_regime import AtrRegime
from src.core.strategies.ema_slope_distance import EmaSlopeDistance
from src.core.strategies.ema_trend import EmaTrend
from src.core.strategies.fibonacci import FibonacciPullback
from src.core.strategies.macd import MacdCross
from src.core.strategies.rsi import RsiReversion
from src.core.strategies.sata_external import SataExternal
from src.core.strategies.sata_parity import SataParity
from src.core.strategies.structure import SrBreakout

BUILTIN_STRATEGIES = (MacdCross, RsiReversion, EmaTrend, AtrRegime,
                      FibonacciPullback, SrBreakout, EmaSlopeDistance, SataParity, SataExternal)
