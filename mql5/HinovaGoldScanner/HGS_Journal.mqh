//+------------------------------------------------------------------+
//| HGS_Journal.mqh — CSV JOURNAL (MQL5\Files\)                      |
//| Writes one line per signal state change, or on manual request.   |
//+------------------------------------------------------------------+
#ifndef HGS_JOURNAL_MQH
#define HGS_JOURNAL_MQH

#include "HGS_Types.mqh"

class CSignalJournal
  {
private:
   int               m_handle;
   string            m_spot;
   string            m_ref;
   static string     MsTimestamp(const long msc);

public:
                     CSignalJournal(void) : m_handle(INVALID_HANDLE) {}
                    ~CSignalJournal(void) { Close(); }
   bool              Open(const string filename, const string spot, const string ref);
   bool              Log(const SScannerSnapshot &s, const ENUM_HGS_SIGNAL from,
                         const ENUM_HGS_SIGNAL to, const string trigger);
   void              Close(void);
  };

//--- "2026.10.16 08:15:42.137" (server time) from a millisecond timestamp
string CSignalJournal::MsTimestamp(const long msc)
  {
   return(TimeToString((datetime)(msc / 1000), TIME_DATE | TIME_SECONDS) +
          StringFormat(".%03d", (int)(msc % 1000)));
  }

//+------------------------------------------------------------------+
bool CSignalJournal::Open(const string filename, const string spot, const string ref)
  {
   m_spot = spot;
   m_ref = ref;
   m_handle = FileOpen(filename, FILE_READ | FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_SHARE_READ, ';');
   if(m_handle == INVALID_HANDLE)
      return(false);
   if(FileSize(m_handle) == 0)
     {
      FileWrite(m_handle, "server_time_ms", "trigger", "from", "to", "spot_symbol", "spot_bid", "spot_ask",
                "ref_symbol", "ref_bid", "ref_ask", "diff", "mean", "deviation_pts", "zscore",
                "spot_spread_pts", "samples", "status");
      FileFlush(m_handle);
     }
   FileSeek(m_handle, 0, SEEK_END);
   return(true);
  }

//+------------------------------------------------------------------+
bool CSignalJournal::Log(const SScannerSnapshot &s, const ENUM_HGS_SIGNAL from,
                         const ENUM_HGS_SIGNAL to, const string trigger)
  {
   if(m_handle == INVALID_HANDLE)
      return(false);
   const int dg = (int)SymbolInfoInteger(m_spot, SYMBOL_DIGITS);
   const int dr = (int)SymbolInfoInteger(m_ref, SYMBOL_DIGITS);
   const uint written = FileWrite(m_handle,
                                  MsTimestamp(s.time_msc), trigger,
                                  HGS_SignalToString(from), HGS_SignalToString(to),
                                  m_spot, DoubleToString(s.spot_bid, dg), DoubleToString(s.spot_ask, dg),
                                  m_ref, DoubleToString(s.ref_bid, dr), DoubleToString(s.ref_ask, dr),
                                  DoubleToString(s.diff, dg), DoubleToString(s.mean, dg),
                                  DoubleToString(s.deviation_pts, 1), DoubleToString(s.zscore, 3),
                                  IntegerToString(s.spot_spread_pts), IntegerToString(s.samples), s.status);
   FileFlush(m_handle);   // a crash or terminal close never loses the last event
   return(written > 0);
  }

void CSignalJournal::Close(void)
  {
   if(m_handle != INVALID_HANDLE)
     {
      FileClose(m_handle);
      m_handle = INVALID_HANDLE;
     }
  }

#endif // HGS_JOURNAL_MQH
