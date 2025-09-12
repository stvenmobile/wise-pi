#define ILI9341_DRIVER
#define LOAD_GLCD     // Built-in 8x16 font

// SPI for LCD (HSPI)
#define USE_HSPI_PORT
#define TFT_MISO 12
#define TFT_MOSI 13
#define TFT_SCLK 14

// LCD control
#define TFT_CS   15
#define TFT_DC    2
#define TFT_RST   4

// Backlight
#define TFT_BL   21
#define TFT_BACKLIGHT_ON HIGH

// (optional) touch
#define TOUCH_CS 33
#define SPI_FREQUENCY       40000000
#define SPI_READ_FREQUENCY  20000000
#define SPI_TOUCH_FREQUENCY 2500000
