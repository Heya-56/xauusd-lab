//+------------------------------------------------------------------+
//| HGS_Scanner.mqh — DATA ENGINE                                    |
//| Calculations only. No chart objects, no file I/O, no orders.     |
//+------------------------------------------------------------------+
#ifndef HGS_SCANNER_MQH
#define HGS_SCANNER_MQH

#include "HGS_Types.mqh"

class CSpreadScanner
  {
private:
   //--- configuration
   string            m_spot;
   string            m_ref;
   ENUM_HGS_MODE     m_mode;
   int               m_window;
   int               m_sample_ms;
   int               m_max_quote_age_ms;
   double            m_z_entry;
   double            m_z_exit;
   double            m_pts_entry;
   double            m_pts_exit;
   double            m_point;
   double            m_min_dev_pts;     // absolute deviation floor (points)
   double            m_cost_mult;       // deviation must exceed cost_mult x broker spread
   int               m_confirm;         // consecutive samples required to enter
   int               m_buy_streak;
   int               m_sell_streak;

   //--- rolling window (ring buffer, O(1) mean / variance)
   double            m_buf[];
   int               m_head;
   int               m_count;
   double            m_sum;
   double            m_sumsq;
   long              m_last_sample_msc;

   //--- state
   SScannerSnapshot  m_snap;
   ENUM_HGS_SIGNAL   m_state;
   ENUM_HGS_SIGNAL   m_prev_published;
   bool              m_changed;

   void              Push(const double v);
   ENUM_HGS_SIGNAL   NextState(const double metric, const double exit_level) const;
   void              Publish(const ENUM_HGS_SIGNAL s);

public:
                     CSpreadScanner(void);
   bool              Init(const string spot, const string ref, const ENUM_HGS_MODE mode,
                          const int window, const int sample_ms, const int max_quote_age_ms,
                          const double z_entry, const double z_exit,
                          const double pts_entry, const double pts_exit,
                          const double min_dev_pts, const double cost_mult, const int confirm_samples);
   void              Evaluate(void);
   void              GetSnapshot(SScannerSnapshot &out) const { out = m_snap; }
   bool              ConsumeChange(ENUM_HGS_SIGNAL &from, ENUM_HGS_SIGNAL &to);
  };

//+------------------------------------------------------------------+
CSpreadScanner::CSpreadScanner(void) : m_buy_streak(0), m_sell_streak(0), m_head(0), m_count(0), m_sum(0.0), m_sumsq(0.0),
   m_last_sample_msc(0), m_state(HGS_NEUTRAL), m_prev_published(HGS_NEUTRAL), m_changed(false)
  {
  }

//+------------------------------------------------------------------+
bool CSpreadScanner::Init(const string spot, const string ref, const ENUM_HGS_MODE mode,
                          const int window, const int sample_ms, const int max_quote_age_ms,
                          const double z_entry, const double z_exit,
                          const double pts_entry, const double pts_exit,
                          const double min_dev_pts, const double cost_mult, const int confirm_samples)
  {
   if(window < 30 || sample_ms < 100 || max_quote_age_ms < 500)
      return(false);
   if(confirm_samples < 1 || min_dev_pts < 0.0 || cost_mult < 0.0)
      return(false);
   m_min_dev_pts = min_dev_pts;
   m_cost_mult = cost_mult;
   m_confirm = confirm_samples;
   m_buy_streak = 0;
   m_sell_streak = 0;
   if(z_exit < 0.0 || z_exit >= z_entry || pts_exit < 0.0 || pts_exit >= pts_entry)
      return(false);
   m_spot = spot;
   m_ref = ref;
   m_mode = mode;
   m_window = window;
   m_sample_ms = sample_ms;
   m_max_quote_age_ms = max_quote_age_ms;
   m_z_entry = z_entry;
   m_z_exit = z_exit;
   m_pts_entry = pts_entry;
   m_pts_exit = pts_exit;
   m_point = SymbolInfoDouble(m_spot, SYMBOL_POINT);
   if(m_point <= 0.0)
      return(false);
   if(ArrayResize(m_buf, m_window) != m_window)
      return(false);
   ArrayInitialize(m_buf, 0.0);
   m_head = 0;
   m_count = 0;
   m_sum = 0.0;
   m_sumsq = 0.0;
   m_last_sample_msc = 0;
   m_state = HGS_NEUTRAL;
   m_prev_published = HGS_NEUTRAL;
   m_changed = false;
   HGS_ResetSnapshot(m_snap, m_window);
   return(true);
  }

//+------------------------------------------------------------------+
//| Add one sample to the ring buffer, keep running sums             |
//+------------------------------------------------------------------+
void CSpreadScanner::Push(const double v)
  {
   if(m_count == m_window)
     {
      const double old = m_buf[m_head];
      m_sum -= old;
      m_sumsq -= old * old;
     }
   else
      m_count++;
   m_buf[m_head] = v;
   m_sum += v;
   m_sumsq += v * v;
   m_head = (m_head + 1) % m_window;
  }

//+------------------------------------------------------------------+
//| Entries need a confirmed streak (counted per SAMPLE, not tick);  |
//| exits back to neutral are immediate (hysteresis on exit level).  |
//+------------------------------------------------------------------+
ENUM_HGS_SIGNAL CSpreadScanner::NextState(const double metric, const double exit_level) const
  {
   const bool buy_ok = (m_buy_streak >= m_confirm);
   const bool sell_ok = (m_sell_streak >= m_confirm);
   if(m_state == HGS_NEUTRAL)
     {
      if(buy_ok)  return(HGS_BUY);
      if(sell_ok) return(HGS_SELL);
      return(HGS_NEUTRAL);
     }
   if(m_state == HGS_BUY)
     {
      if(sell_ok)               return(HGS_SELL);
      if(metric >= -exit_level) return(HGS_NEUTRAL);
      return(HGS_BUY);
     }
   // m_state == HGS_SELL
   if(buy_ok)               return(HGS_BUY);
   if(metric <= exit_level) return(HGS_NEUTRAL);
   return(HGS_SELL);
  }

//+------------------------------------------------------------------+
void CSpreadScanner::Publish(const ENUM_HGS_SIGNAL s)
  {
   m_state = s;
   m_snap.signal = s;
   if(s != m_prev_published)
      m_changed = true;
  }

//+------------------------------------------------------------------+
//| Main computation. Called from OnTick (spot ticks) and OnTimer    |
//| (catches reference-only moves). Cheap: O(1) per call.            |
//+------------------------------------------------------------------+
void CSpreadScanner::Evaluate(void)
  {
   MqlTick ts, tr;
   m_snap.samples = m_count;
   if(!SymbolInfoTick(m_spot, ts) || !SymbolInfoTick(m_ref, tr))
     {
      m_snap.ready = false;
      m_snap.status = "NO_TICK";
      Publish(HGS_NEUTRAL);
      return;
     }
   m_snap.time_msc = ts.time_msc;
   m_snap.spot_bid = ts.bid;
   m_snap.spot_ask = ts.ask;
   m_snap.ref_bid = tr.bid;
   m_snap.ref_ask = tr.ask;
   m_snap.spot_spread_pts = (long)MathRound((ts.ask - ts.bid) / m_point);

   if(ts.bid <= 0.0 || ts.ask < ts.bid || tr.bid <= 0.0 || tr.ask < tr.bid)
     {
      m_snap.ready = false;
      m_snap.status = "BAD_QUOTE";
      Publish(HGS_NEUTRAL);
      return;
     }

   //--- Fail closed when one feed is stale relative to the other (e.g. CME pause)
   const long age = MathAbs(ts.time_msc - tr.time_msc);
   const double diff = (ts.bid + ts.ask) * 0.5 - (tr.bid + tr.ask) * 0.5;
   m_snap.diff = diff;
   if(age > m_max_quote_age_ms)
     {
      m_snap.ready = false;
      m_snap.status = "STALE_REF";
      Publish(HGS_NEUTRAL);
      return;
     }

   //--- Sample at a fixed cadence so busy tick periods do not dominate the statistics
   const long now = MathMax(ts.time_msc, tr.time_msc);
   bool sampled = false;
   if(now - m_last_sample_msc >= m_sample_ms)
     {
      Push(diff);
      m_last_sample_msc = now;
      sampled = true;
     }
   m_snap.samples = m_count;

   if(m_count < m_window)
     {
      m_snap.ready = false;
      m_snap.status = "WARMUP";
      Publish(HGS_NEUTRAL);
      return;
     }

   const double mean = m_sum / m_count;
   const double var = MathMax(m_sumsq / m_count - mean * mean, 0.0);
   const double sd = MathSqrt(var);
   const double dev = diff - mean;
   m_snap.mean = mean;
   m_snap.stdev = sd;
   m_snap.deviation_pts = dev / m_point;
   m_snap.zscore = (sd > 0.0) ? dev / sd : 0.0;
   m_snap.ready = (sd > 0.0);
   m_snap.status = m_snap.ready ? "OK" : "FLAT";

   if(!m_snap.ready)
     {
      Publish(HGS_NEUTRAL);
      return;
     }
   const double metric = (m_mode == HGS_MODE_ZSCORE) ? m_snap.zscore : m_snap.deviation_pts;
   const double entry = (m_mode == HGS_MODE_ZSCORE) ? m_z_entry : m_pts_entry;
   const double exit_level = (m_mode == HGS_MODE_ZSCORE) ? m_z_exit : m_pts_exit;

   //--- Gates (advance once per sample): the deviation must exceed both a fixed floor
   //    and a multiple of the broker spread, and persist for m_confirm samples.
   if(sampled)
     {
      const double min_pts = MathMax(m_min_dev_pts, m_cost_mult * (double)m_snap.spot_spread_pts);
      const bool big = (MathAbs(m_snap.deviation_pts) >= min_pts);
      m_buy_streak  = (metric <= -entry && big) ? m_buy_streak + 1 : 0;
      m_sell_streak = (metric >=  entry && big) ? m_sell_streak + 1 : 0;
     }
   Publish(NextState(metric, exit_level));
  }

//+------------------------------------------------------------------+
//| Returns true once per state change (for the journal)             |
//+------------------------------------------------------------------+
bool CSpreadScanner::ConsumeChange(ENUM_HGS_SIGNAL &from, ENUM_HGS_SIGNAL &to)
  {
   if(!m_changed)
      return(false);
   from = m_prev_published;
   to = m_snap.signal;
   m_prev_published = m_snap.signal;
   m_changed = false;
   return(true);
  }

#endif // HGS_SCANNER_MQH
