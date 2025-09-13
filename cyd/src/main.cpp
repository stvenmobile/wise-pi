#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <TFT_eSPI.h>

#include "secrets.h"

// Safety net if someone forgot to create secrets.h
#ifndef WIFI_SSID
  #warning "WIFI_SSID not defined; using placeholder."
  #define WIFI_SSID     "YOUR_SSID"
#endif
#ifndef WIFI_PASSWORD
  #warning "WIFI_PASSWORD not defined; using placeholder."
  #define WIFI_PASSWORD "YOUR_PASSWORD"
#endif


// ===== Theme =====
static const uint16_t BG_COLOR = TFT_BLACK;
static const uint16_t FG_COLOR = TFT_WHITE;

// ===== Pins =====
#ifndef TFT_BL
  #define TFT_BL 21        // your confirmed working backlight pin
#endif
static const int LDR_PIN = 39;   // confirmed LDR ADC pin

// ===== Backlight PWM =====
static const int BL_CH   = 2;
static const int BL_BITS = 8;
static const int BL_FREQ = 5000;
static const uint8_t BL_MIN = 24;   // floor to keep panel lit
static const uint8_t BL_MAX = 255;  // full blast

// LDR behavior toggles
#define USE_LDR    1   // set to 0 to force fixed BL at BL_MAX
#define LDR_INVERT 0   // if brighter room makes screen dimmer, set to 1

// ===== Quote refresh cadence =====
static const uint32_t REFRESH_MS = 60 * 1000UL;

// ===== Layout / typography =====
static const int PAD = 10;             // outer padding
static const uint8_t TXT_SIZE = 2;     // GLCD size 2

// ===== Globals =====
TFT_eSPI tft;
uint32_t lastRefresh = 0;

// ===== Utils =====
static inline int charW(uint8_t sz){ return 6 * sz; }     // GLCD font width/char
static inline int lineH(uint8_t sz){ return (8 * sz) + 6; } // +6 breathing room
static inline void dbg(const String& s){ Serial.println(s); }

static void setBacklight(uint8_t level) {
  level = constrain(level, BL_MIN, BL_MAX);
  ledcWrite(BL_CH, level);
}

// ===== Self-calibrating backlight from LDR =====
void updateBacklight() {
#if USE_LDR
  static float bl_ema = BL_MAX;
  static uint16_t ldr_min = 4095, ldr_max = 0;
  static uint32_t lastLog = 0;
  static uint8_t  bad_streak = 0;
  static bool     ldr_ok = true;

  analogSetPinAttenuation(LDR_PIN, ADC_11db);
  int raw = analogRead(LDR_PIN);   // 0..4095

  // Persistently railed values -> treat sensor as bad
  bool extreme = (raw <= 5 || raw >= 4090);
  bad_streak = extreme ? (uint8_t)min<int>(255, bad_streak + 1) : 0;
  if (bad_streak > 20) ldr_ok = false;

  // Learn working range with gentle decay so old extremes fade
  if (!extreme) {
    ldr_min = min<uint16_t>(ldr_min, (uint16_t)raw);
    ldr_max = max<uint16_t>(ldr_max, (uint16_t)raw);
    // decay toward current sample
    ldr_min = (uint16_t)((ldr_min * 9 + raw) / 10);
    ldr_max = (uint16_t)((ldr_max * 9 + raw) / 10);
  }

  // Seed sensible defaults until we learn a span
  uint16_t lo = (ldr_min == 4095 ? 20  : ldr_min);
  uint16_t hi = (ldr_max == 0    ? 200 : ldr_max);
  if (hi - lo < 40) { lo = max<int>(lo - 10, 0); hi = lo + 40; }

  if (!ldr_ok) {
    setBacklight(200);
    if (millis() - lastLog > 2000) {
      dbg("LDR invalid -> fixed BL=200 (raw=" + String(raw) + ")");
      lastLog = millis();
    }
    return;
  }

  // Normalize raw to 0..1 within learned span
  float norm = (float)(raw - lo) / (float)(hi - lo);
  norm = constrain(norm, 0.0f, 1.0f);

  // Map to BL range (invert if wiring polarity demands it)
  int target = LDR_INVERT
               ? (int)(BL_MIN + (1.0f - norm) * (BL_MAX - BL_MIN))
               : (int)(BL_MIN + norm * (BL_MAX - BL_MIN));

  // Smooth and apply
  bl_ema = 0.85f * bl_ema + 0.15f * target;
  setBacklight((uint8_t)bl_ema);

  if (millis() - lastLog > 2000) {
    dbg("LDR=" + String(raw) +
        " map[" + String(lo) + ".." + String(hi) + "] -> BL=" + String((int)bl_ema));
    lastLog = millis();
  }
#else
  setBacklight(BL_MAX);
#endif
}

// ===== Word wrap: returns next Y after the last drawn line =====
int drawWrappedWords(const String& text, int x, int y, int w,
                     uint8_t textSize, uint16_t fg, uint16_t bg)
{
  tft.setTextColor(fg, bg);
  tft.setTextFont(1);
  tft.setTextSize(textSize);
  tft.setTextWrap(false);

  const int maxChars = max(1, w / charW(textSize));
  const int lh = lineH(textSize);
  int cy = y;

  String word, line;

  auto flushLine = [&](){
    tft.setCursor(x, cy);
    tft.print(line);
    cy += lh;
    line = "";
  };

  auto pushWord = [&](const String& wtok){
    if (wtok.length() == 0) return;

    // If single word is longer than a line, hard-break (rare)
    if ((int)wtok.length() > maxChars) {
      int start = 0;
      while (start < (int)wtok.length()) {
        int chunk = min(maxChars, (int)wtok.length() - start);
        tft.setCursor(x, cy);
        tft.print(wtok.substring(start, start + chunk));
        cy += lh;
        start += chunk;
      }
      return;
    }

    if (line.length() == 0) {
      line = wtok;
    } else {
      int needed = (int)line.length() + 1 + (int)wtok.length();
      if (needed <= maxChars) {
        line += ' ';
        line += wtok;
      } else {
        flushLine();
        line = wtok;
      }
    }
  };

  for (int i=0, n=text.length(); i<n; ++i) {
    char c = text[i];
    if (c == '\n') {
      if (word.length()) { pushWord(word); word = ""; }
      if (line.length()) flushLine();
      continue;
    }
    if (c == ' ' || c == '\t' || c == '\r') {
      pushWord(word);
      word = "";
    } else {
      word += c;
    }
  }
  if (word.length()) pushWord(word);
  if (line.length()) flushLine();

  return cy;
}

// ===== Networking =====
bool fetchQuote(String& quoteOut, String& authorOut, String& errOut) {
  errOut = "";
  quoteOut = "";
  authorOut = "";

  if (WiFi.status() != WL_CONNECTED) {
    errOut = "No Wi-Fi connection.";
    return false;
  }

  WiFiClientSecure client; client.setInsecure();
  HTTPClient https; https.setTimeout(6000);
  const char* url = "https://zenquotes.io/api/random";

  dbg(String("HTTP GET: ") + url);

  if (!https.begin(client, url)) {
    errOut = "HTTPS begin() failed.";
    return false;
  }

  int code = https.GET();
  dbg("HTTP status: " + String(code));

  if (code == HTTP_CODE_OK) {
    String payload = https.getString();
    JsonDocument doc;   // ArduinoJson v7
    auto err = deserializeJson(doc, payload);
    if (!err && doc.is<JsonArray>() && doc.size() > 0) {
      JsonObject o = doc[0];
      quoteOut  = o["q"].as<String>();
      authorOut = o["a"].as<String>();
      https.end();
      return true;
    } else {
      errOut = "JSON parse error.";
    }
  } else {
    errOut = "HTTP error " + String(code);
  }

  https.end();
  return false;
}

void connectWiFi() {
  if (String(WIFI_SSID) == "YOUR_SSID") {
    dbg("Wi-Fi skipped: set WIFI_SSID/WIFI_PASSWORD");
    return;
  }

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  dbg("Wi-Fi connecting to " + String(WIFI_SSID));

  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - start) < 15000) {
    delay(200);
  }

  if (WiFi.status() == WL_CONNECTED) {
    dbg("Wi-Fi connected, IP=" + WiFi.localIP().toString());
  } else {
    dbg("Wi-Fi connect timeout");
  }
}

// ===== Rendering =====
void clearScreen() {
  tft.fillScreen(BG_COLOR);
  tft.setTextFont(1);
  tft.setTextSize(TXT_SIZE);
  tft.setTextColor(FG_COLOR, BG_COLOR);
}

void showQuote(const String& quote, const String& author) {
  clearScreen();

  // top blank line
  const int topBlank = lineH(TXT_SIZE);

  // enforce at least one character column blank on the right
  const int usableW = tft.width() - PAD*2 - charW(TXT_SIZE);

  const int tx = PAD;
  int y = PAD + topBlank;

  // wrap quote
  String q = String("“") + quote + "”";
  int nextY = drawWrappedWords(q, tx, y, usableW, TXT_SIZE, FG_COLOR, BG_COLOR);

  // one blank line between quote and author
  nextY += lineH(TXT_SIZE);

  // author
  tft.setCursor(tx, nextY);
  tft.print("- " + author);
}

void showError(const String& msg) {
  clearScreen();
  const int usableW = tft.width() - PAD*2 - charW(TXT_SIZE);
  const int tx = PAD;
  const int y  = PAD + lineH(TXT_SIZE); // keep a blank line at the top
  drawWrappedWords("Error: " + msg, tx, y, usableW, TXT_SIZE, FG_COLOR, BG_COLOR);
}

// ===== Arduino =====
void setup() {
  Serial.begin(115200);
  delay(100);
  dbg("\nBoot");

  // Backlight first
  pinMode(TFT_BL, OUTPUT);
  ledcSetup(BL_CH, BL_FREQ, BL_BITS);
  ledcAttachPin(TFT_BL, BL_CH);
  setBacklight(BL_MAX);
  dbg("Backlight on (PWM)");

  // TFT
  tft.init();
  tft.setRotation(1);   // landscape
  dbg("TFT init OK, w=" + String(tft.width()) + " h=" + String(tft.height()) + " rot=1");

  // Wi-Fi
  connectWiFi();

  // First quote (or error)
  String quote, author, err;
  if (fetchQuote(quote, author, err)) {
    showQuote(quote, author);
  } else {
    dbg("Fetch failed: " + err);
    showError(err);
  }

  lastRefresh = millis();
}

void loop() {
  static uint32_t lastBL = 0;
  if (millis() - lastBL > 100) {
    updateBacklight();
    lastBL = millis();
  }

  if (millis() - lastRefresh > REFRESH_MS) {
    dbg("Refreshing quote…");
    String quote, author, err;
    if (fetchQuote(quote, author, err)) {
      showQuote(quote, author);
    } else {
      dbg("Refresh failed: " + err);
      showError(err);
    }
    lastRefresh = millis();
  }

  delay(5);
}
