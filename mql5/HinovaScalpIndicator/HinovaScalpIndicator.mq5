//+------------------------------------------------------------------+
//| HinovaScalpIndicator.mq5                                         |
//| Indicateur de scalping XAUUSD (M1-M15). N'EXÉCUTE AUCUN ORDRE.   |
//| Code original Hinova Digital - aucune source tierce reprise.     |
//|                                                                  |
//| Logique (bougies clôturées uniquement, shift >= 1) :             |
//|  Tendance : EMA rapide > EMA lente (achat) / < (vente)           |
//|  Déclencheur : la bougie clôturée repasse au-dessus (sous) de    |
//|                l'EMA rapide après l'avoir touchée (pullback)     |
//|  Filtres : ATR >= seuil (marché vivant), spread <= max,          |
//|            session horaire serveur autorisée                     |
//|  Niveaux indicatifs : SL = k*ATR, TP = R * SL (affichage seul)   |
//+------------------------------------------------------------------+
#property copyright   "Hinova Digital"
#property link        "https://hinovadigitalcorp.com"
#property version     "1.00"
#property description "Scalping XAUUSD : flèches sur bougies clôturées. Indicateur seulement, aucun ordre."
#property indicator_chart_window
#property indicator_buffers 4
#property indicator_plots   4

#property indicator_label1  "EMA rapide"
#property indicator_type1   DRAW_LINE
#property indicator_color1  clrGold
#property indicator_width1  1
#property indicator_label2  "EMA lente"
#property indicator_type2   DRAW_LINE
#property indicator_color2  clrSteelBlue
#property indicator_width2  1
#property indicator_label3  "Achat"
#property indicator_type3   DRAW_ARROW
#property indicator_color3  clrLimeGreen
#property indicator_width3  2
#property indicator_label4  "Vente"
#property indicator_type4   DRAW_ARROW
#property indicator_color4  clrTomato
#property indicator_width4  2

input int    InpFastEma      = 9;      // EMA rapide
input int    InpSlowEma      = 50;     // EMA lente (tendance)
input int    InpAtrPeriod    = 14;     // Période ATR
input double InpMinAtr       = 0.80;   // ATR minimum (en prix, ex. 0.80 $)
input int    InpMaxSpreadPts = 40;     // Spread max (points) pour signaler
input int    InpSessionStart = 7;      // Heure serveur début (incluse)
input int    InpSessionEnd   = 20;     // Heure serveur fin (exclue)
input double InpSlAtr        = 1.5;    // SL indicatif = k * ATR
input double InpRR           = 1.5;    // TP indicatif = R * SL
input bool   InpAlert        = false;  // Alerte popup sur nouveau signal
input int    InpCooldownBars = 5;      // Barres minimum entre deux signaux

double BufFast[], BufSlow[], BufBuy[], BufSell[];
int    hFast = INVALID_HANDLE, hSlow = INVALID_HANDLE, hAtr = INVALID_HANDLE;
datetime lastAlertBar = 0;

int OnInit()
{
   if(InpFastEma < 2 || InpSlowEma <= InpFastEma || InpAtrPeriod < 2 || InpSlAtr <= 0 || InpRR <= 0)
      return INIT_PARAMETERS_INCORRECT;
   SetIndexBuffer(0, BufFast, INDICATOR_DATA);
   SetIndexBuffer(1, BufSlow, INDICATOR_DATA);
   SetIndexBuffer(2, BufBuy,  INDICATOR_DATA);
   SetIndexBuffer(3, BufSell, INDICATOR_DATA);
   PlotIndexSetInteger(2, PLOT_ARROW, 233);
   PlotIndexSetInteger(3, PLOT_ARROW, 234);
   for(int p = 0; p < 4; p++) PlotIndexSetDouble(p, PLOT_EMPTY_VALUE, EMPTY_VALUE);
   ArraySetAsSeries(BufFast, false); ArraySetAsSeries(BufSlow, false);
   ArraySetAsSeries(BufBuy, false);  ArraySetAsSeries(BufSell, false);

   hFast = iMA(_Symbol, _Period, InpFastEma, 0, MODE_EMA, PRICE_CLOSE);
   hSlow = iMA(_Symbol, _Period, InpSlowEma, 0, MODE_EMA, PRICE_CLOSE);
   hAtr  = iATR(_Symbol, _Period, InpAtrPeriod);
   if(hFast == INVALID_HANDLE || hSlow == INVALID_HANDLE || hAtr == INVALID_HANDLE)
      return INIT_FAILED;
   if(StringFind(_Symbol, "XAU") < 0 && StringFind(_Symbol, "GOLD") < 0)
      Print("HinovaScalp : conçu pour XAUUSD, symbole actuel ", _Symbol);
   IndicatorSetString(INDICATOR_SHORTNAME, "HinovaScalp (aucun ordre)");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(hFast != INVALID_HANDLE) IndicatorRelease(hFast);
   if(hSlow != INVALID_HANDLE) IndicatorRelease(hSlow);
   if(hAtr  != INVALID_HANDLE) IndicatorRelease(hAtr);
   ObjectsDeleteAll(0, "HSI_");
   Comment("");
}

bool InSession(datetime t)
{
   MqlDateTime d; TimeToStruct(t, d);
   if(InpSessionStart <= InpSessionEnd) return d.hour >= InpSessionStart && d.hour < InpSessionEnd;
   return d.hour >= InpSessionStart || d.hour < InpSessionEnd;     // session à cheval sur minuit
}

int OnCalculate(const int rates_total, const int prev_calculated, const datetime &time[],
                const double &open[], const double &high[], const double &low[], const double &close[],
                const long &tick_volume[], const long &volume[], const int &spread[])
{
   int need = InpSlowEma + InpAtrPeriod + 2;
   if(rates_total < need) return 0;

   static double atr[];
   ArraySetAsSeries(atr, false);
   if(CopyBuffer(hFast, 0, 0, rates_total, BufFast) != rates_total) return 0;
   if(CopyBuffer(hSlow, 0, 0, rates_total, BufSlow) != rates_total) return 0;
   if(CopyBuffer(hAtr,  0, 0, rates_total, atr)     != rates_total) return 0;

   int start = (prev_calculated > need) ? prev_calculated - 2 : need;
   int last  = rates_total - 2;              // dernière bougie CLÔTURÉE ; la bougie en cours n'est jamais signalée
   BufBuy[rates_total - 1] = EMPTY_VALUE; BufSell[rates_total - 1] = EMPTY_VALUE;

   for(int i = start; i <= last; i++)
   {
      BufBuy[i] = EMPTY_VALUE; BufSell[i] = EMPTY_VALUE;
      if(atr[i] < InpMinAtr || spread[i] > InpMaxSpreadPts || !InSession(time[i])) continue;

      bool cooldown = false;
      for(int k = 1; k <= InpCooldownBars && i - k >= 0; k++)
         if(BufBuy[i - k] != EMPTY_VALUE || BufSell[i - k] != EMPTY_VALUE) { cooldown = true; break; }
      if(cooldown) continue;

      bool up = BufFast[i] > BufSlow[i] && BufFast[i - 1] > BufSlow[i - 1];
      bool dn = BufFast[i] < BufSlow[i] && BufFast[i - 1] < BufSlow[i - 1];
      // pullback : la bougie précédente a touché l'EMA rapide, la bougie i clôture du bon côté avec un corps directionnel
      if(up && low[i - 1] <= BufFast[i - 1] && close[i] > BufFast[i] && close[i] > open[i])
         BufBuy[i] = low[i] - 0.3 * atr[i];
      else if(dn && high[i - 1] >= BufFast[i - 1] && close[i] < BufFast[i] && close[i] < open[i])
         BufSell[i] = high[i] + 0.3 * atr[i];
   }

   // panneau d'information sur la dernière bougie clôturée
   string state = "Aucun signal";
   double sl = InpSlAtr * atr[last], tp = InpRR * sl;
   if(BufBuy[last]  != EMPTY_VALUE) state = StringFormat("ACHAT indicatif  SL %.2f  TP %.2f", close[last] - sl, close[last] + tp);
   if(BufSell[last] != EMPTY_VALUE) state = StringFormat("VENTE indicative  SL %.2f  TP %.2f", close[last] + sl, close[last] - tp);
   Comment(StringFormat("HinovaScalp — indicateur seulement, aucun ordre\nATR %.2f | spread %d pts | session %s\n%s",
           atr[last], spread[last], InSession(time[last]) ? "ouverte" : "fermée", state));

   if(InpAlert && time[last] != lastAlertBar && (BufBuy[last] != EMPTY_VALUE || BufSell[last] != EMPTY_VALUE))
   {
      lastAlertBar = time[last];
      Alert(_Symbol, " ", EnumToString(_Period), " HinovaScalp : ", state);
   }
   return rates_total;
}
