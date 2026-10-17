//+------------------------------------------------------------------+
//| HinovaExportCSV.mq5 — SCRIPT (pas un EA)                         |
//| Exporte les bougies CLÔTURÉES du graphique en CSV pour le lab.   |
//| Aucun ordre, aucune requête réseau. Fichier écrit dans           |
//| <Dossier des données>/MQL5/Files/                                |
//+------------------------------------------------------------------+
#property copyright "Hinova Digital"
#property version   "1.00"
#property script_show_inputs
#property description "Export CSV des bougies clôturées (ts UTC, open, high, low, close, spread). Aucun ordre."

input int    InpBars      = 50000;   // Nombre de bougies (max dispo si plus)
input string InpInstrType = "cfd";   // cfd ou spot (jamais futures)

void OnStart()
{
   // Décalage serveur -> UTC, arrondi à 15 min (les brokers sont en UTC+2/+3)
   long offset = (long)(TimeTradeServer() - TimeGMT());
   offset = (long)MathRound(offset / 900.0) * 900;

   MqlRates r[];
   ArraySetAsSeries(r, false);
   int got = CopyRates(_Symbol, _Period, 1, InpBars, r);     // départ à 1 : la bougie en cours est exclue
   if(got <= 0) { Alert("Export impossible : aucune bougie. Faites défiler le graphique vers la gauche pour charger l'historique."); return; }

   string tf   = StringSubstr(EnumToString(_Period), 7);      // PERIOD_M15 -> M15
   string name = StringFormat("hinova_%s_%s.csv", _Symbol, tf);
   int h = FileOpen(name, FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
   if(h == INVALID_HANDLE) { Alert("Impossible de créer ", name, " (erreur ", GetLastError(), ")"); return; }

   FileWrite(h, StringFormat("# symbol=%s;timeframe=%s;instrument_type=%s;source=mt5:%s;broker_server=%s;server_utc_offset_s=%d;exported_utc=%s",
             _Symbol, tf, InpInstrType, AccountInfoString(ACCOUNT_COMPANY), AccountInfoString(ACCOUNT_SERVER),
             offset, TimeToString(TimeGMT(), TIME_DATE | TIME_SECONDS)));
   FileWrite(h, "ts", "open", "high", "low", "close", "spread");
   for(int i = 0; i < got; i++)
      FileWrite(h, (long)r[i].time - offset,
                DoubleToString(r[i].open, _Digits), DoubleToString(r[i].high, _Digits),
                DoubleToString(r[i].low, _Digits),  DoubleToString(r[i].close, _Digits),
                DoubleToString(r[i].spread * _Point, _Digits));
   FileClose(h);
   Alert(StringFormat("Export OK : %d bougies -> MQL5/Files/%s", got, name));
}
