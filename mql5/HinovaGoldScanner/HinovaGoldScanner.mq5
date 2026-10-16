//+------------------------------------------------------------------+
//| HinovaGoldScanner.mq5                                            |
//| Decision-support scanner: XAUUSD vs a reference gold symbol.     |
//|                                                                  |
//| THIS EA NEVER TRADES. It includes no trade library, calls no     |
//| OrderSend / CTrade, and only: computes a signal, shows it, and   |
//| journals it to CSV. All decisions remain with the trader.        |
//|                                                                  |
//| Architecture (strict separation):                                |
//|   HGS_Scanner.mqh   data engine  -> SScannerSnapshot             |
//|   HGS_Dashboard.mqh UI           <- reads snapshot (OnTimer)     |
//|   HGS_Journal.mqh   CSV journal  <- reads snapshot on change     |
//+------------------------------------------------------------------+
#property copyright "Hinova Digital"
#property link      "https://hinovadigitalcorp.com"
#property version   "1.00"
#property description "Scanner d'aide à la décision XAUUSD / référence (Z-score). N'exécute AUCUN ordre."

#include "HGS_Types.mqh"
#include "HGS_Scanner.mqh"
#include "HGS_Dashboard.mqh"
#include "HGS_Journal.mqh"

//--- inputs
input group "Symboles"
input string        InpRefSymbol      = "GC";            // Symbole de référence (nom exact chez votre broker)
input group "Signal"
input ENUM_HGS_MODE InpMode           = HGS_MODE_ZSCORE; // Méthode
input int           InpWindow         = 600;             // Échantillons dans la fenêtre glissante
input int           InpSampleMs       = 1000;            // Cadence d'échantillonnage (ms)
input double        InpZEntry         = 2.0;             // Z-score d'entrée
input double        InpZExit          = 0.5;             // Z-score de retour au neutre
input double        InpPtsEntry       = 150.0;           // Déviation d'entrée (points, mode fixe)
input double        InpPtsExit        = 50.0;            // Déviation de sortie (points, mode fixe)
input int           InpMaxQuoteAgeMs  = 5000;            // Décalage max entre les deux cotations (ms)
input group "Interface et journal"
input int           InpUiRefreshMs    = 500;             // Rafraîchissement du panneau (ms)
input int           InpPanelX         = 20;
input int           InpPanelY         = 40;
input string        InpJournalFile    = "HinovaGoldScanner_journal.csv"; // Fichier dans MQL5\Files

//--- the three independent modules
CSpreadScanner  g_engine;
CDashboard      g_ui;
CSignalJournal  g_journal;
bool            g_journal_ok = false;

//+------------------------------------------------------------------+
//| Make sure the reference symbol is in Market Watch and synced     |
//+------------------------------------------------------------------+
bool EnsureSymbolReady(const string symbol)
  {
   bool custom = false;
   if(!SymbolExist(symbol, custom))
     {
      PrintFormat("[HGS] Symbole '%s' introuvable chez ce broker.", symbol);
      return(false);
     }
   if(!SymbolInfoInteger(symbol, SYMBOL_SELECT) && !SymbolSelect(symbol, true))
     {
      PrintFormat("[HGS] Impossible d'ajouter '%s' au Market Watch (erreur %d).", symbol, GetLastError());
      return(false);
     }
   for(int i = 0; i < 30 && !SymbolIsSynchronized(symbol); i++)   // up to ~3 s
      Sleep(100);
   if(!SymbolIsSynchronized(symbol))
      PrintFormat("[HGS] '%s' pas encore synchronisé : le scanner restera en attente (NO_TICK/WARMUP).", symbol);
   return(true);
  }

//+------------------------------------------------------------------+
int OnInit(void)
  {
   if(InpRefSymbol == _Symbol)
     {
      Print("[HGS] Le symbole de référence doit être différent du symbole du graphique.");
      return(INIT_PARAMETERS_INCORRECT);
     }
   if(InpUiRefreshMs < 100)
     {
      Print("[HGS] Rafraîchissement trop rapide (minimum 100 ms).");
      return(INIT_PARAMETERS_INCORRECT);
     }
   if(!EnsureSymbolReady(InpRefSymbol))
      return(INIT_PARAMETERS_INCORRECT);

   if(!g_engine.Init(_Symbol, InpRefSymbol, InpMode, InpWindow, InpSampleMs, InpMaxQuoteAgeMs,
                     InpZEntry, InpZExit, InpPtsEntry, InpPtsExit))
     {
      Print("[HGS] Paramètres du moteur invalides (fenêtre >= 30, sortie < entrée, ages >= 500 ms).");
      return(INIT_PARAMETERS_INCORRECT);
     }

   g_journal_ok = g_journal.Open(InpJournalFile, _Symbol, InpRefSymbol);
   if(!g_journal_ok)
      PrintFormat("[HGS] Journal indisponible (%s, erreur %d). Le scanner continue sans journal.",
                  InpJournalFile, GetLastError());

   if(!g_ui.Create(ChartID(), InpPanelX, InpPanelY, _Symbol, InpRefSymbol))
     {
      g_ui.Destroy();
      Print("[HGS] Création du panneau impossible.");
      return(INIT_FAILED);
     }

   if(!EventSetMillisecondTimer(InpUiRefreshMs))
     {
      g_ui.Destroy();
      Print("[HGS] Timer indisponible.");
      return(INIT_FAILED);
     }
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
//| Engine step + journal on state change. Shared by tick and timer. |
//+------------------------------------------------------------------+
void RunEngine(void)
  {
   g_engine.Evaluate();
   ENUM_HGS_SIGNAL from = HGS_NEUTRAL, to = HGS_NEUTRAL;
   if(g_engine.ConsumeChange(from, to) && g_journal_ok)
     {
      SScannerSnapshot snap;
      g_engine.GetSnapshot(snap);
      g_journal.Log(snap, from, to, "signal_change");
     }
  }

//--- Data path: every spot tick. No UI work here.
void OnTick(void)
  {
   RunEngine();
  }

//--- UI path at a fixed cadence. Also re-runs the engine so a move of the
//    reference symbol alone (which does not fire OnTick) is taken into account.
void OnTimer(void)
  {
   RunEngine();
   SScannerSnapshot snap;
   g_engine.GetSnapshot(snap);
   g_ui.Update(snap);
  }

//--- Manual button: journal the current state on demand
void OnChartEvent(const int id, const long &lparam, const double &dparam, const string &sparam)
  {
   if(id == CHARTEVENT_OBJECT_CLICK && g_ui.IsManualButton(sparam))
     {
      SScannerSnapshot snap;
      g_engine.GetSnapshot(snap);
      if(g_journal_ok)
         g_journal.Log(snap, snap.signal, snap.signal, "manual");
      g_ui.ReleaseButton();
     }
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   EventKillTimer();
   g_ui.Destroy();
   g_journal.Close();
  }
