// Receptor de frames por serial
// Recibe frames de 1024 bytes y los vuelca DIRECTO al buffer de la pantalla.
// SIN buffers intermedios ni Strings: el Uno tiene 2KB SRAM y el buffer ya ocupa 1024.
//
// Protocolo:
//   Mac -> Uno: [0xAA][0x55] + 1024 bytes (formato buffer de pantalla).
//   Uno -> Mac: 1 byte de ACK tras cada frame: 'K' = ok, 'T' = timeout de Wire.
//   El header magico permite re-sincronizar si se pierde un byte; el ACK le da
//   control de flujo real a Python (esperar ACK antes del proximo frame).
//
// Wire timeout: el Wire de AVR NO tiene timeout por defecto; si el bus I2C
// glitchea, display() se cuelga para siempre. setWireTimeout lo evita.
//
// Baudios: 115200 (el Uno soporta hasta 500000 con 0% de error).

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SH110X.h>

#define SCREEN_WIDTH  128
#define SCREEN_HEIGHT 64
#define OLED_RESET    -1
#define OLED_ADDR     0x3C
#define FRAME_BYTES   1024

// GME12864 = controlador SH1106 (NO SSD1306). getBuffer() lo aporta la base
// Adafruit_GrayOLED, asi que el volcado directo al buffer funciona igual.
Adafruit_SH1106G display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

// Lectura bloqueante de un byte del serial.
static inline uint8_t readByte() {
  while (Serial.available() == 0) { /* espera */ }
  return (uint8_t)Serial.read();
}

void setup() {
  Serial.begin(115200);
  Wire.begin();
  Wire.setClock(400000);            // I2C 400 kHz
  Wire.setWireTimeout(25000, true); // 25ms timeout + reset del bus si se cuelga

  if (!display.begin(OLED_ADDR, true)) {
    pinMode(LED_BUILTIN, OUTPUT);
    for (;;) { digitalWrite(LED_BUILTIN, HIGH); delay(100); digitalWrite(LED_BUILTIN, LOW); delay(100); }
  }
  display.clearDisplay();
  display.display();
}

void loop() {
  // 1) Sincronizacion: buscar header 0xAA 0x55.
  if (readByte() != 0xAA) return;   // no era header: volver a buscar
  if (readByte() != 0x55) return;

  // 2) GOTCHA SH110X: display() solo transmite la region "sucia" marcada por
  //    las funciones GFX. Escribir getBuffer() directo NO la marca -> display()
  //    no mandaria NADA. clearDisplay() marca la pantalla entera como sucia
  //    (y el memset es despreciable) antes de pisar el buffer con el frame.
  display.clearDisplay();

  // 3) Leer 1024 bytes DIRECTO sobre el buffer interno de la libreria.
  uint8_t *buf = display.getBuffer();
  for (uint16_t i = 0; i < FRAME_BYTES; i++) {
    buf[i] = readByte();
  }

  // 4) Volcar el buffer a la pantalla por I2C y avisar (ACK).
  // Health-check: ping I2C a la OLED. Un NACK (cable suelto) NO dispara el
  // wire timeout, asi que hay que probarlo explicitamente.
  Wire.clearWireTimeoutFlag();
  display.display();
  if (Wire.getWireTimeoutFlag()) {
    Serial.write('T');              // bus colgado (hubo timeout)
  } else {
    Wire.beginTransmission(OLED_ADDR);
    Serial.write(Wire.endTransmission() == 0 ? 'K' : 'N');  // N = OLED no responde
  }
}
