//+------------------------------------------------------------------+
//| HinovaBridge.mq5                                                 |
//| Sends CLOSED candles + non-secret account state to the Hinova    |
//| API and displays the returned proposal (BUY / SELL / NO_TRADE).  |
//|                                                                  |
//| THIS EA NEVER TRADES. No trade library is included and no order  |
//| function is called. The broker account, password and funds stay  |
//| with the trader. Payload format: payload.example.json.           |
//|                                                                  |
//| Setup: Tools > Options > Expert Advisors > "Allow WebRequest for |
//| listed URL" and add the API origin (e.g. https://api.example).   |
//+------------------------------------------------------------------+
#property copyright "Hinova Digital"
#property link      "https://hinovadigitalcorp.com"
#property version   "1.00"
#property description "Pont Hinova Trading Lab : envoie les bougies clôturées, affiche la proposition. N'exécute AUCUN ordre."

input string          InpApiUrl        = "https://api.example.com"; // URL de l'API Hinova (sans / final)
input string          InpTerminalKey   = "";                        // Clé de terminal (htl_...) depuis « Mon compte »
input ENUM_TIMEFRAMES InpTimeframe     = PERIOD_M15;                // Unité de temps envoyée (doit égaler celle du profil)
input int             InpBars          = 400;                       // Bougies clôturées envoyées (100-2000)
input string          InpInstrumentType = "cfd";                    // cfd ou spot (jamais futures)
input int             InpPollSeconds   = 15;                        // Vérification d'une nouvelle bougie (s)
input int             InpTimeoutMs     = 5000;                      // Délai max de la requête HTTP

#define HB_PREFIX "HB_"

datetime g_last_sent_bar = 0;
string   g_decision      = "—";
string   g_status        = "INIT";
long     g_expires_at    = 0;

//+------------------------------------------------------------------+
string TfName(const ENUM_TIMEFRAMES tf)
  {
   switch(tf)
     {
      case PERIOD_M1:  return("M1");
      case PERIOD_M5:  return("M5");
      case PERIOD_M15: return("M15");
      case PERIOD_M30: return("M30");
      case PERIOD_H1:  return("H1");
      case PERIOD_H4:  return("H4");
      case PERIOD_D1:  return("D1");
      default:         return("");
     }
  }

//--- JSON-safe string (escape quotes, backslashes and control characters)
string Js(const string s)
  {
   string out = s;
   StringReplace(out, "\\", "\\\\");
   StringReplace(out, "\"", "\\\"");
   StringReplace(out, "\r", " ");
   StringReplace(out, "\n", " ");
   StringReplace(out, "\t", " ");
   return("\"" + out + "\"");
  }

//--- Broker server offset to UTC, rounded to the nearest 15 minutes.
//    H4/D1 bars keep the broker's own phase (e.g. 22:00 UTC opens); the engine
//    accepts any phase as long as it is constant across the series.
long ServerUtcOffset(void)
  {
   const long raw = (long)(TimeTradeServer() - TimeGMT());
   return((long)MathRound(raw / 900.0) * 900);
  }

//--- Realised P/L of deals closed today, in % of balance (non-secret)
double DailyPnlPct(void)
  {
   const double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   if(balance <= 0.0)
      return(0.0);
   MqlDateTime d;
   TimeToStruct(TimeTradeServer(), d);
   d.hour = 0; d.min = 0; d.sec = 0;
   if(!HistorySelect(StructToTime(d), TimeTradeServer()))
      return(0.0);
   double pnl = 0.0;
   const int n = HistoryDealsTotal();
   for(int i = 0; i < n; i++)
     {
      const ulong t = HistoryDealGetTicket(i);
      if(t == 0)
         continue;
      if(HistoryDealGetInteger(t, DEAL_ENTRY) == DEAL_ENTRY_IN)
         continue;
      pnl += HistoryDealGetDouble(t, DEAL_PROFIT) + HistoryDealGetDouble(t, DEAL_SWAP) + HistoryDealGetDouble(t, DEAL_COMMISSION);
     }
   return(100.0 * pnl / balance);
  }

//--- Open positions on this symbol (count only)
int OpenPositionsOnSymbol(void)
  {
   int n = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
      if(PositionGetSymbol(i) == _Symbol)
         n++;
   return(n);
  }

//--- Extract "key":"value" (string) from a flat JSON response
string JsonString(const string body, const string key)
  {
   const string pat = "\"" + key + "\":\"";
   const int p = StringFind(body, pat);
   if(p < 0)
      return("");
   const int s = p + StringLen(pat);
   const int e = StringFind(body, "\"", s);
   return(e > s ? StringSubstr(body, s, e - s) : "");
  }

long JsonLong(const string body, const string key)
  {
   const string pat = "\"" + key + "\":";
   const int p = StringFind(body, pat);
   if(p < 0)
      return(0);
   return(StringToInteger(StringSubstr(body, p + StringLen(pat), 20)));
  }

//+------------------------------------------------------------------+
//| Build the payload from CLOSED bars only (shift >= 1)             |
//+------------------------------------------------------------------+
bool BuildPayload(string &json, datetime &last_bar)
  {
   MqlRates r[];
   ArraySetAsSeries(r, false);
   const int got = CopyRates(_Symbol, InpTimeframe, 1, InpBars, r);   // shift 1 = last closed bar
   if(got < 10)
      return(false);
   const long off = ServerUtcOffset();
   const int dg = _Digits;
   string candles = "";
   for(int i = 0; i < got; i++)
     {
      const long ts = (long)r[i].time - off;
      if(i > 0)
         candles += ",";
      candles += StringFormat("{\"ts\":%I64d,\"open\":%s,\"high\":%s,\"low\":%s,\"close\":%s,\"volume\":%I64d,\"spread\":%s}",
                              ts, DoubleToString(r[i].open, dg), DoubleToString(r[i].high, dg),
                              DoubleToString(r[i].low, dg), DoubleToString(r[i].close, dg),
                              r[i].tick_volume, DoubleToString(r[i].spread * _Point, dg));
     }
   last_bar = r[got - 1].time;
   const double spread_now = SymbolInfoDouble(_Symbol, SYMBOL_ASK) - SymbolInfoDouble(_Symbol, SYMBOL_BID);
   const string source = "mt5:" + AccountInfoString(ACCOUNT_COMPANY) + ":" + AccountInfoString(ACCOUNT_SERVER);
   const string idem = StringFormat("tm-%I64d-%I64d", AccountInfoInteger(ACCOUNT_LOGIN) % 100000, (long)last_bar - off);
   json = StringFormat("{\"schema_version\":\"1.0\",\"idempotency_key\":%s,\"request_ts\":%I64d,"
                       "\"provenance\":{\"symbol\":\"XAUUSD\",\"instrument_type\":%s,\"timeframe\":%s,\"source\":%s},"
                       "\"candles\":[%s],"
                       "\"account\":{\"open_positions\":%d,\"daily_pnl_pct\":%s,\"current_spread\":%s}}",
                       Js(idem), (long)TimeGMT(), Js(InpInstrumentType), Js(TfName(InpTimeframe)), Js(source),
                       candles, OpenPositionsOnSymbol(), DoubleToString(DailyPnlPct(), 4), DoubleToString(spread_now, dg));
   return(true);
  }

//+------------------------------------------------------------------+
void Render(void)
  {
   color c = clrWhite;
   if(g_decision == "BUY")  c = clrLimeGreen;
   if(g_decision == "SELL") c = clrTomato;
   const long left = g_expires_at > 0 ? g_expires_at - (long)TimeGMT() : 0;
   string valid = (g_expires_at > 0 && left > 0) ? StringFormat("valable %d s", left) : "expirée";
   if(g_decision == "—" || g_decision == "NO_TRADE") valid = "";
   ObjectSetString(0, HB_PREFIX "sig", OBJPROP_TEXT, "Hinova : " + g_decision + "  " + valid);
   ObjectSetInteger(0, HB_PREFIX "sig", OBJPROP_COLOR, c);
   ObjectSetString(0, HB_PREFIX "st", OBJPROP_TEXT, g_status + " · aucun ordre automatique");
   ChartRedraw(0);
  }

void Label(const string id, const int y, const int size)
  {
   const string n = HB_PREFIX + id;
   ObjectCreate(0, n, OBJ_LABEL, 0, 0, 0);
   ObjectSetInteger(0, n, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, n, OBJPROP_XDISTANCE, 20);
   ObjectSetInteger(0, n, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, n, OBJPROP_FONTSIZE, size);
   ObjectSetString(0, n, OBJPROP_FONT, "Segoe UI Semibold");
   ObjectSetInteger(0, n, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, n, OBJPROP_HIDDEN, true);
   ObjectSetInteger(0, n, OBJPROP_COLOR, clrSilver);
  }

//+------------------------------------------------------------------+
//| Send once per new closed bar. Any failure => NO_TRADE shown.     |
//+------------------------------------------------------------------+
void SendIfNewBar(void)
  {
   const datetime closed = iTime(_Symbol, InpTimeframe, 1);
   if(closed == 0 || closed == g_last_sent_bar)
      return;
   string payload;
   datetime last_bar;
   if(!BuildPayload(payload, last_bar))
     {
      g_status = "HISTORIQUE_INSUFFISANT";
      return;
     }
   char data[], result[];
   string resp_headers;
   const int nbytes = StringToCharArray(payload, data, 0, WHOLE_ARRAY, CP_UTF8);
   if(nbytes > 0)
      ArrayResize(data, nbytes - 1);              // drop the terminating NUL (invalid in JSON)
   const string headers = "Content-Type: application/json\r\nAuthorization: Bearer " + InpTerminalKey + "\r\n";
   ResetLastError();
   const int code = WebRequest("POST", InpApiUrl + "/v1/ea/signal", headers, InpTimeoutMs, data, result, resp_headers);
   const string body = CharArrayToString(result, 0, WHOLE_ARRAY, CP_UTF8);
   g_last_sent_bar = closed;                         // one attempt per bar: no hammering on errors
   if(code == -1)
     {
      g_decision = "NO_TRADE";
      g_status = StringFormat("RÉSEAU (erreur %d : URL autorisée ?)", GetLastError());
     }
   else if(code != 200)
     {
      g_decision = "NO_TRADE";
      const string err = JsonString(body, "error");
      g_status = StringFormat("HTTP %d %s", code, err);
     }
   else
     {
      const string d = JsonString(body, "decision");
      g_expires_at = JsonLong(body, "expires_at");
      g_decision = (d == "BUY" || d == "SELL") ? d : "NO_TRADE";   // anything unexpected => NO_TRADE
      g_status = "OK " + JsonString(body, "risk_status");
     }
   Render();
  }

//+------------------------------------------------------------------+
int OnInit(void)
  {
   if(StringLen(InpTerminalKey) < 24 || StringFind(InpTerminalKey, "htl_") != 0)
     {
      Print("[HinovaBridge] Clé de terminal manquante ou invalide (doit commencer par htl_).");
      return(INIT_PARAMETERS_INCORRECT);
     }
   if(StringFind(InpApiUrl, "https://") != 0)
     {
      Print("[HinovaBridge] L'URL de l'API doit être en HTTPS.");
      return(INIT_PARAMETERS_INCORRECT);
     }
   if(TfName(InpTimeframe) == "" || InpBars < 100 || InpBars > 2000 || InpPollSeconds < 5 || InpTimeoutMs > 10000)
     {
      Print("[HinovaBridge] Paramètres invalides.");
      return(INIT_PARAMETERS_INCORRECT);
     }
   if(InpInstrumentType != "cfd" && InpInstrumentType != "spot")
     {
      Print("[HinovaBridge] InpInstrumentType doit être cfd ou spot.");
      return(INIT_PARAMETERS_INCORRECT);
     }
   Label("sig", 30, 12);
   Label("st", 54, 8);
   Render();
   EventSetTimer(InpPollSeconds);
   return(INIT_SUCCEEDED);
  }

void OnTimer(void)
  {
   SendIfNewBar();
   Render();   // refresh the validity countdown
  }

void OnTick(void)
  {
   // Intentionally empty: requests run from the timer so ticks are never blocked.
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   ObjectsDeleteAll(0, HB_PREFIX);
   ChartRedraw(0);
  }
