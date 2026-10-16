//+------------------------------------------------------------------+
//| HGS_Types.mqh — shared data contract between Engine, UI, Journal |
//| Hinova Gold Scanner. Pure data: no calculations, no graphics.    |
//+------------------------------------------------------------------+
#ifndef HGS_TYPES_MQH
#define HGS_TYPES_MQH

//--- Raw signal published by the engine (values fixed by the spec)
enum ENUM_HGS_SIGNAL
  {
   HGS_NEUTRAL = 0,   // no opportunity
   HGS_BUY     = 1,   // spot cheap versus reference (negative deviation)
   HGS_SELL    = 2    // spot rich versus reference (positive deviation)
  };

//--- How the deviation is compared to the thresholds
enum ENUM_HGS_MODE
  {
   HGS_MODE_ZSCORE = 0,        // (diff - mean) / stdev
   HGS_MODE_FIXED_POINTS = 1   // (diff - mean) expressed in points of the chart symbol
  };

//--- Immutable snapshot the engine hands to the UI and to the journal.
//    The UI and the journal only READ this; they never compute anything.
struct SScannerSnapshot
  {
   long              time_msc;        // server time of the spot tick (ms)
   double            spot_bid;
   double            spot_ask;
   double            ref_bid;
   double            ref_ask;
   double            diff;            // mid(spot) - mid(ref), price units
   double            mean;            // rolling mean of diff
   double            stdev;           // rolling standard deviation of diff
   double            deviation_pts;   // (diff - mean) in points of the spot symbol
   double            zscore;          // (diff - mean) / stdev
   long              spot_spread_pts; // broker spread on the spot symbol (points)
   int               samples;         // samples currently in the rolling window
   int               window;          // window size required before signalling
   ENUM_HGS_SIGNAL   signal;
   bool              ready;           // enough samples AND fresh, valid quotes
   string            status;          // OK, WARMUP, STALE_REF, NO_TICK, BAD_QUOTE
  };

//--- Explicit reset (avoids ZeroMemory on a struct that holds a string)
void HGS_ResetSnapshot(SScannerSnapshot &s, const int window)
  {
   s.time_msc = 0;
   s.spot_bid = 0.0;
   s.spot_ask = 0.0;
   s.ref_bid = 0.0;
   s.ref_ask = 0.0;
   s.diff = 0.0;
   s.mean = 0.0;
   s.stdev = 0.0;
   s.deviation_pts = 0.0;
   s.zscore = 0.0;
   s.spot_spread_pts = 0;
   s.samples = 0;
   s.window = window;
   s.signal = HGS_NEUTRAL;
   s.ready = false;
   s.status = "INIT";
  }

string HGS_SignalToString(const ENUM_HGS_SIGNAL s)
  {
   switch(s)
     {
      case HGS_BUY:  return("BUY");
      case HGS_SELL: return("SELL");
      default:       return("NEUTRE");
     }
  }

#endif // HGS_TYPES_MQH
