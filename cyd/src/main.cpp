#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <TFT_eSPI.h>
#include <XPT2046_Touchscreen.h>

TFT_eSPI tft;

#ifndef DEFAULT_BG
  #define DEFAULT_BG 0x0171
#endif
#ifndef DEFAULT_FG
  #define DEFAULT_FG 0xFFFF
#endif

// ---- WiFi ----
const char* WIFI_SSID = "YOUR_SSID";
const char* WIFI_PASS = "YOUR_PASS";

// ---- Touch ----
#define TOUCH_CS   12
#define TOUCH_IRQ  36
XPT2046_Touchscreen ts(TOUCH_CS, TOUCH_IRQ);

// ---- Settings ----
struct UiSettings {
  uint16_t bg = DEFAULT_BG;
  uint16_t fg = DEFAULT_FG;
  uint8_t  font = 2;   // TFT built-ins: 2 or 4 recommended
  uint8_t  size = 1;   // 1..3
} ui;

Preferences prefs;
WiFiClientSecure net;

const uint16_t COLOR_CHOICES[][2] = {
  {0x0000, 0xFFFF}, // black/white
  {0xFFFF, 0x0000}, // white/black
  {0x0171, 0xFFFF}, // dark blue/white (default)
  {0x7BEF, 0x0000}, // gray/black
};
const char* COLOR_NAMES[] = {"Blk/Wht","Wht/Blk","Blue/Wht","Gray/Blk"};
const uint8_t  FONT_CHOICES[] = {2,4};
const char*    FONT_NAMES[]   = {"Font2","Font4"};
const uint8_t  SIZE_CHOICES[] = {1,2,3};

void saveSettings(){
  prefs.begin("wise-cyd", false);
  prefs.putUShort("bg", ui.bg);
  prefs.putUShort("fg", ui.fg);
  prefs.putUChar("font", ui.font);
  prefs.putUChar("size", ui.size);
  prefs.end();
}
void loadSettings(){
  prefs.begin("wise-cyd", true);
  ui.bg   = prefs.getUShort("bg", ui.bg);
  ui.fg   = prefs.getUShort("fg", ui.fg);
  ui.font = prefs.getUChar("font", ui.font);
  ui.size = prefs.getUChar("size", ui.size);
  prefs.end();
}

void applyUi(){
  tft.fillScreen(ui.bg);
  tft.setTextColor(ui.fg, ui.bg);
  tft.setTextFont(ui.font);
  tft.setTextSize(ui.size);
  tft.setTextDatum(TL_DATUM);
}

String fetchQuote(){
  HTTPClient http;
  net.setInsecure(); // TODO: pin CA in prod
  if (!http.begin(net, "https://zenquotes.io/api/random")) return "";
  int code = http.GET();
  if (code != HTTP_CODE_OK) { http.end(); return ""; }
  String body = http.getString();
  http.end();

  StaticJsonDocument<1024> doc;
  if (deserializeJson(doc, body)) return "";
  String q = doc[0]["q"].as<String>();
  String a = doc[0]["a"].asString();
  return q + "\n— " + a;
}

void wrapPrint(const String& text, int x, int y, int w, int lineH){
  int cx=x, cy=y; String word, line;
  for (size_t i=0;i<=text.length();++i){
    char c = (i<text.length()) ? text[i] : '\n';
    if (c==' ' || c=='\n'){
      String trial = line + (line.length() ? " " : "") + word;
      if (tft.textWidth(trial) > w && line.length()){
        tft.drawString(line, cx, cy); cy += lineH; line = word;
      } else line = trial;
      word = "";
      if (c=='\n'){ tft.drawString(line,cx,cy); cy += lineH; line=""; }
    } else word += c;
  }
  if (line.length()) tft.drawString(line, cx, cy);
}

void showQuote(const String& text){
  applyUi();
  int margin = 12;
  int lineH = (ui.font==4 ? 28 : 22) * ui.size;
  wrapPrint(text, margin, margin, tft.width()-2*margin, lineH);
}

void wifiConnect(){
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis()-t0 < 15000) delay(200);
}

bool tapIn(int16_t x,int16_t y,int16_t rx,int16_t ry,int16_t rw,int16_t rh){
  return (x>=rx && x<rx+rw && y>=ry && y<ry+rh);
}

void drawSetup(uint8_t ic,uint8_t ifo,uint8_t isz){
  applyUi();
  tft.drawString("Wise-CYD Setup", 10, 8);
  tft.drawString("Color:", 10, 40); tft.drawString(COLOR_NAMES[ic], 120, 40);
  tft.drawString("Font:",  10, 70); tft.drawString(FONT_NAMES[ifo], 120, 70);
  tft.drawString("Size:",  10,100); tft.drawString(String(SIZE_CHOICES[isz]),120,100);
  tft.drawString("Tap rows to cycle; long-tap Save", 10, 140);
}

void setupScreen(){
  // map current to indices
  uint8_t ic=2, ifo= (ui.font==4)?1:0, isz= (ui.size==3)?2:(ui.size==2)?1:0;
  for (uint8_t i=0;i<4;i++) if (COLOR_CHOICES[i][0]==ui.bg && COLOR_CHOICES[i][1]==ui.fg) { ic=i; break; }

  drawSetup(ic,ifo,isz);

  unsigned long endAt = millis()+20000; // 20s window
  while (millis() < endAt){
    if (ts.touched()){
      TS_Point p = ts.getPoint(); // raw; TFT_eSPI uses rotation(1)
      // crude map for 320x240 landscape; most CYDs have correct mapping after setRotation(1)
      int16_t x = p.y; // swap if needed
      int16_t y = 320 - p.x;

      if (tapIn(x,y, 0,30, 320,24)) { ic=(ic+1)%4; ui.bg=COLOR_CHOICES[ic][0]; ui.fg=COLOR_CHOICES[ic][1]; drawSetup(ic,ifo,isz); }
      else if (tapIn(x,y,0,60,320,24)) { ifo=(ifo+1)%2; ui.font=FONT_CHOICES[ifo]; drawSetup(ic,ifo,isz); }
      else if (tapIn(x,y,0,90,320,24)) { isz=(isz+1)%3; ui.size=SIZE_CHOICES[isz]; drawSetup(ic,ifo,isz); }
      else if (tapIn(x,y,0,130,320,30)) { saveSettings(); return; }
      delay(200);
    }
    delay(10);
  }
  saveSettings();
}

void setup(){
  // Backlight on
  pinMode(TFT_BL, OUTPUT); digitalWrite(TFT_BL, HIGH);

  tft.init();
  tft.setRotation(1); // landscape
  ts.begin();         // XPT2046
  // Optional: ts.setRotation(1);  // try 1/3 if axes feel inverted

  loadSettings();
  applyUi();

  // Hold touch at boot (or briefly tap) to enter setup
  if (ts.touched()) setupScreen();

  wifiConnect();
  String qt = fetchQuote();
  if (qt.isEmpty()) qt = "Network error.\n— Wise-Pi";
  showQuote(qt);
}

void loop(){
  delay(30UL*60UL*1000UL); // 30 min
  String qt = fetchQuote();
  if (!qt.isEmpty()) showQuote(qt);
}
