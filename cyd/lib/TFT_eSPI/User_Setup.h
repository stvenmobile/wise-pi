#pragma once
// ==== Display driver ====
#define ILI9341_DRIVER
#define TFT_WIDTH  240
#define TFT_HEIGHT 320

// ==== ESP32 VSPI pins (shared with touch/SD) ====
#define TFT_MOSI 23
#define TFT_MISO 19
#define TFT_SCLK 18
#define TFT_CS    5    // LCD CS
#define TFT_DC   27    // LCD DC
#define TFT_RST  -1    // tied to EN; use -1

// Backlight (PWM-capable)
#define TFT_BL   32
#define TFT_BACKLIGHT_ON HIGH

// ==== Touch (XPT2046) ====
#define TOUCH_CS   12
#define TOUCH_IRQ  36  // T_IRQ (Input only)

// ==== SD (onboard) - optional ====
#define SD_CS      13

// ==== SPI frequency ====
#define SPI_FREQUENCY        40000000
#define SPI_READ_FREQUENCY   20000000
#define SPI_TOUCH_FREQUENCY   2500000

// Rotate 90° (landscape) by default; code may call setRotation(1)
