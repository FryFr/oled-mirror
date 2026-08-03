// Hola mundo OLED (GME12864, controlador SH1106)
// Verifica cableado I2C y direccion. La libreria es Adafruit SH110X (NO SSD1306):
// este panel usa un controlador SH1106, no SSD1306.
// Cableado: SDA -> A4, SCL -> A5, VCC -> 5V, GND -> GND.
// Si no muestra nada con SH1106G: probar Adafruit_SH1107, o direccion 0x3D.

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SH110X.h>

#define SCREEN_WIDTH  128
#define SCREEN_HEIGHT 64
#define OLED_RESET    -1
#define OLED_ADDR     0x3C   // tipico modulos eBay/GME; alternativa 0x3D

Adafruit_SH1106G display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

void setup() {
  Serial.begin(115200);
  Wire.begin();
  Wire.setClock(400000);

  if (!display.begin(OLED_ADDR, true)) {
    pinMode(LED_BUILTIN, OUTPUT);
    for (;;) {
      digitalWrite(LED_BUILTIN, HIGH); delay(200);
      digitalWrite(LED_BUILTIN, LOW);  delay(200);
    }
  }

  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SH110X_WHITE);
  display.setCursor(0, 0);
  display.println(F("oled-mirror"));
  display.println(F("Hello: OK SH1106"));
  display.print(F("addr 0x"));
  display.println(OLED_ADDR, HEX);
  display.println(F("128x64 I2C 400kHz"));

  display.drawRect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, SH110X_WHITE);
  display.display();
}

void loop() {
}
