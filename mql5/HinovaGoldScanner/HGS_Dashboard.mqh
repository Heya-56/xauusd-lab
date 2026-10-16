//+------------------------------------------------------------------+
//| HGS_Dashboard.mqh — USER INTERFACE                               |
//| Renders an SScannerSnapshot with lightweight native objects.     |
//| No calculations: it only formats values the engine produced.     |
//+------------------------------------------------------------------+
#ifndef HGS_DASHBOARD_MQH
#define HGS_DASHBOARD_MQH

#include "HGS_Types.mqh"

#define HGS_W        300
#define HGS_ROW      20
#define HGS_PAD      12

class CDashboard
  {
private:
   long              m_chart;
   string            m_prefix;
   int               m_x;
   int               m_y;
   string            m_spot;
   string            m_ref;
   bool              m_dirty;

   string            N(const string id) const { return(m_prefix + id); }
   bool              Rect(const string id, const int x, const int y, const int w, const int h,
                          const color bg, const color border);
   bool              Text(const string id, const int x, const int y, const string text,
                          const color clr, const int size, const string font = "Consolas");
   void              SetText(const string id, const string text);
   void              SetColor(const string id, const color clr);
   void              SetBg(const string id, const color clr);

public:
                     CDashboard(void) : m_chart(0), m_dirty(false) {}
   bool              Create(const long chart, const int x, const int y, const string spot, const string ref);
   void              Update(const SScannerSnapshot &s);
   bool              IsManualButton(const string object_name) const { return(object_name == N("btn")); }
   void              ReleaseButton(void);
   void              Destroy(void);
  };

//+------------------------------------------------------------------+
bool CDashboard::Rect(const string id, const int x, const int y, const int w, const int h,
                      const color bg, const color border)
  {
   const string n = N(id);
   if(!ObjectCreate(m_chart, n, OBJ_RECTANGLE_LABEL, 0, 0, 0))
      return(false);
   ObjectSetInteger(m_chart, n, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(m_chart, n, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(m_chart, n, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(m_chart, n, OBJPROP_XSIZE, w);
   ObjectSetInteger(m_chart, n, OBJPROP_YSIZE, h);
   ObjectSetInteger(m_chart, n, OBJPROP_BGCOLOR, bg);
   ObjectSetInteger(m_chart, n, OBJPROP_BORDER_TYPE, BORDER_FLAT);
   ObjectSetInteger(m_chart, n, OBJPROP_COLOR, border);
   ObjectSetInteger(m_chart, n, OBJPROP_BACK, false);
   ObjectSetInteger(m_chart, n, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(m_chart, n, OBJPROP_HIDDEN, true);
   return(true);
  }

//+------------------------------------------------------------------+
bool CDashboard::Text(const string id, const int x, const int y, const string text,
                      const color clr, const int size, const string font)
  {
   const string n = N(id);
   if(!ObjectCreate(m_chart, n, OBJ_LABEL, 0, 0, 0))
      return(false);
   ObjectSetInteger(m_chart, n, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(m_chart, n, OBJPROP_ANCHOR, ANCHOR_LEFT_UPPER);
   ObjectSetInteger(m_chart, n, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(m_chart, n, OBJPROP_YDISTANCE, y);
   ObjectSetString(m_chart, n, OBJPROP_TEXT, text);
   ObjectSetString(m_chart, n, OBJPROP_FONT, font);
   ObjectSetInteger(m_chart, n, OBJPROP_FONTSIZE, size);
   ObjectSetInteger(m_chart, n, OBJPROP_COLOR, clr);
   ObjectSetInteger(m_chart, n, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(m_chart, n, OBJPROP_HIDDEN, true);
   return(true);
  }

//--- Setters touch the chart only when the value really changes (no useless redraws)
void CDashboard::SetText(const string id, const string text)
  {
   const string n = N(id);
   if(ObjectGetString(m_chart, n, OBJPROP_TEXT) != text)
     {
      ObjectSetString(m_chart, n, OBJPROP_TEXT, text);
      m_dirty = true;
     }
  }

void CDashboard::SetColor(const string id, const color clr)
  {
   const string n = N(id);
   if((color)ObjectGetInteger(m_chart, n, OBJPROP_COLOR) != clr)
     {
      ObjectSetInteger(m_chart, n, OBJPROP_COLOR, clr);
      m_dirty = true;
     }
  }

void CDashboard::SetBg(const string id, const color clr)
  {
   const string n = N(id);
   if((color)ObjectGetInteger(m_chart, n, OBJPROP_BGCOLOR) != clr)
     {
      ObjectSetInteger(m_chart, n, OBJPROP_BGCOLOR, clr);
      m_dirty = true;
     }
  }

//+------------------------------------------------------------------+
bool CDashboard::Create(const long chart, const int x, const int y, const string spot, const string ref)
  {
   m_chart = chart;
   m_x = x;
   m_y = y;
   m_spot = spot;
   m_ref = ref;
   m_prefix = StringFormat("HGS_%I64d_", chart);   // unique per chart, removed on deinit
   ObjectsDeleteAll(m_chart, m_prefix);            // clean leftovers from a crashed session

   const color bg = C'11,19,34', border = C'47,65,102', muted = C'110,127,158', text = C'232,238,249';
   const int lx = x + HGS_PAD, vx = x + 150;
   int r = y + HGS_PAD;
   bool ok = Rect("bg", x, y, HGS_W, 300, bg, border);
   ok = (Text("title", lx, r, "HINOVA GOLD SCANNER", C'46,230,214', 10, "Segoe UI Semibold")) && ok; r += 24;
   ok = (Text("mode", lx, r, "Aide à la décision · aucun ordre", muted, 8, "Segoe UI")) && ok;     r += 26;
   ok = (Text("k_spot", lx, r, m_spot, muted, 9)) && ok;          ok = (Text("v_spot", vx, r, "—", text, 9)) && ok; r += HGS_ROW;
   ok = (Text("k_ref", lx, r, m_ref, muted, 9)) && ok;            ok = (Text("v_ref", vx, r, "—", text, 9)) && ok;  r += HGS_ROW;
   ok = (Text("k_diff", lx, r, "Écart (spot-réf)", muted, 9)) && ok; ok = (Text("v_diff", vx, r, "—", text, 9)) && ok; r += HGS_ROW;
   ok = (Text("k_dev", lx, r, "Déviation (pts)", muted, 9)) && ok;   ok = (Text("v_dev", vx, r, "—", text, 9)) && ok;  r += HGS_ROW;
   ok = (Text("k_z", lx, r, "Z-score", muted, 9)) && ok;          ok = (Text("v_z", vx, r, "—", text, 9)) && ok;    r += HGS_ROW;
   ok = (Text("k_spr", lx, r, "Spread broker", muted, 9)) && ok;  ok = (Text("v_spr", vx, r, "—", text, 9)) && ok;  r += HGS_ROW + 6;
   ok = (Rect("sig_bg", lx, r, HGS_W - 2 * HGS_PAD, 34, C'26,37,64', border)) && ok;
   ok = (Text("sig", lx + 10, r + 8, "NEUTRE", clrWhite, 12, "Segoe UI Semibold")) && ok;
   ok = (Text("status", lx + 130, r + 11, "INIT", muted, 8)) && ok; r += 46;

   const string b = N("btn");
   ok = (ObjectCreate(m_chart, b, OBJ_BUTTON, 0, 0, 0)) && ok;
   if(ok)
     {
      ObjectSetInteger(m_chart, b, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(m_chart, b, OBJPROP_XDISTANCE, lx);
      ObjectSetInteger(m_chart, b, OBJPROP_YDISTANCE, r);
      ObjectSetInteger(m_chart, b, OBJPROP_XSIZE, HGS_W - 2 * HGS_PAD);
      ObjectSetInteger(m_chart, b, OBJPROP_YSIZE, 26);
      ObjectSetString(m_chart, b, OBJPROP_TEXT, "Noter dans le journal");
      ObjectSetString(m_chart, b, OBJPROP_FONT, "Segoe UI");
      ObjectSetInteger(m_chart, b, OBJPROP_FONTSIZE, 9);
      ObjectSetInteger(m_chart, b, OBJPROP_BGCOLOR, C'230,184,74');
      ObjectSetInteger(m_chart, b, OBJPROP_COLOR, C'26,20,5');
      ObjectSetInteger(m_chart, b, OBJPROP_BORDER_COLOR, C'230,184,74');
      ObjectSetInteger(m_chart, b, OBJPROP_STATE, false);
      ObjectSetInteger(m_chart, b, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(m_chart, b, OBJPROP_HIDDEN, true);
     }
   r += 36;
   ObjectSetInteger(m_chart, N("bg"), OBJPROP_YSIZE, r - y);
   ChartRedraw(m_chart);
   return(ok);
  }

//+------------------------------------------------------------------+
//| Pure rendering of a snapshot. Called from OnTimer only.          |
//+------------------------------------------------------------------+
void CDashboard::Update(const SScannerSnapshot &s)
  {
   const int dg = (int)SymbolInfoInteger(m_spot, SYMBOL_DIGITS);
   const int dr = (int)SymbolInfoInteger(m_ref, SYMBOL_DIGITS);
   SetText("v_spot", s.spot_bid > 0 ? DoubleToString(s.spot_bid, dg) + " / " + DoubleToString(s.spot_ask, dg) : "—");
   SetText("v_ref",  s.ref_bid  > 0 ? DoubleToString(s.ref_bid, dr)  + " / " + DoubleToString(s.ref_ask, dr)  : "—");
   SetText("v_diff", DoubleToString(s.diff, dg));
   SetText("v_dev",  s.ready ? DoubleToString(s.deviation_pts, 0) : "—");
   SetText("v_z",    s.ready ? DoubleToString(s.zscore, 2) : "—");
   SetText("v_spr",  IntegerToString(s.spot_spread_pts) + " pts");

   color c = clrWhite, bg = C'26,37,64';
   if(s.signal == HGS_BUY)  { c = clrWhite; bg = C'22,128,61'; }
   if(s.signal == HGS_SELL) { c = clrWhite; bg = C'185,28,28'; }
   if(!s.ready)             { c = C'148,163,184'; bg = C'26,37,64'; }
   SetText("sig", HGS_SignalToString(s.signal));
   SetColor("sig", c);
   SetBg("sig_bg", bg);
   string st = s.status;
   if(s.status == "WARMUP")
      st = StringFormat("WARMUP %d/%d", s.samples, s.window);
   SetText("status", st);

   if(m_dirty)
     {
      ChartRedraw(m_chart);
      m_dirty = false;
     }
  }

//+------------------------------------------------------------------+
void CDashboard::ReleaseButton(void)
  {
   ObjectSetInteger(m_chart, N("btn"), OBJPROP_STATE, false);
   ChartRedraw(m_chart);
  }

void CDashboard::Destroy(void)
  {
   if(m_prefix != "")
      ObjectsDeleteAll(m_chart, m_prefix);
   ChartRedraw(m_chart);
  }

#endif // HGS_DASHBOARD_MQH
