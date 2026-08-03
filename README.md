# oled-mirror 🪞

Un espejo en vivo de **1024 píxeles**: la cámara de la Mac te captura, Python
procesa el video en tiempo real y lo dibuja sobre una pantalla OLED de
**128×64** conectada a un **Arduino Uno** por puerto serial.

> 📸 _[Fotos y video demo próximamente]_

## Cómo funciona

```
┌─────────────────────── Mac (Python) ───────────────────────┐
│ OpenCV captura → grises → espejo → crop 2:1 → 128×64       │
│ → contraste → dithering Floyd-Steinberg (1-bit)            │
│ → serial: [0xAA][0x55] + 1024 bytes (con pacing)           │
└──────────────────────────┬─────────────────────────────────┘
                           │ USB serial 115200
┌──────────────────────────▼─────────────────────────────────┐
│ Arduino Uno: busca header → escribe los 1024 bytes DIRECTO │
│ en el buffer de la librería → display() → ACK              │
└──────────────────────────┬─────────────────────────────────┘
                           │ I2C 400kHz
                    OLED SH1106 128×64
```

**~6 fps** estables a 115200 baudios (techo físico ≈ 11 fps a ese baudrate).

## Hardware

| Componente | Detalle |
|---|---|
| Arduino Uno | 2KB SRAM — y el frame ocupa 1024 bytes 😅 |
| OLED GME12864 | Controlador **SH1106** (¡no SSD1306!), I2C addr `0x3C` |
| Cableado | SDA→A4 · SCL→A5 · VCC→5V · GND→GND |

## Instalación

```bash
# Arduino
brew install arduino-cli
arduino-cli config init
arduino-cli core install arduino:avr
arduino-cli lib install "Adafruit SH110X"

# Python (3.12 — MediaPipe aún no tiene wheels para 3.14)
python3.12 -m venv venv
./venv/bin/pip install -r requirements.txt
```

## Uso

```bash
# 1. Detectar el puerto del Uno
arduino-cli board list

# 2. Verificar cableado con el hola mundo
arduino-cli compile --fqbn arduino:avr:uno arduino/oled_hello
arduino-cli upload  --fqbn arduino:avr:uno -p <PUERTO> arduino/oled_hello

# 3. Subir el receptor de frames
arduino-cli compile --fqbn arduino:avr:uno arduino/oled_receiver
arduino-cli upload  --fqbn arduino:avr:uno -p <PUERTO> arduino/oled_receiver

# 4. (Opcional) Probar el pipeline con un patrón fijo
./venv/bin/python python/send_test_pattern.py --port <PUERTO>

# 5. ¡El espejo!
./venv/bin/python python/mirror.py --port <PUERTO>
```

La primera vez, macOS pide permiso de cámara para tu terminal
(Ajustes → Privacidad y seguridad → Cámara).

## Protocolo serial

```
Mac → Uno:  [0xAA][0x55] + 1024 bytes (8 pages × 128 columnas)
Uno → Mac:  1 byte de ACK: 'K' ok · 'N' OLED no responde · 'T' timeout I2C
```

- El **header mágico** permite re-sincronizar si se pierde un byte.
- El **ACK** es control de flujo real: Python no envía el siguiente frame
  hasta que el Uno confirmó el anterior. Además hace un ping I2C a la OLED,
  así que detecta hasta un cable flojo.
- El Uno escribe los bytes recibidos **directo sobre el buffer de la librería**
  (`display.getBuffer()`): con 2KB de SRAM no hay lugar para buffers intermedios.

## Los dos bugs que casi nos vuelven locos 🐛

Documentados porque **le van a pasar a cualquiera** que replique esto:

### 1. El dirty window de Adafruit SH110X

A diferencia de `Adafruit_SSD1306`, en la librería SH110X `display()` **solo
transmite la región "sucia"** que fue marcada por funciones GFX (`drawPixel`,
`println`...). Si escribís `getBuffer()` directo, la librería no se entera:
`display()` termina "exitoso", el I2C responde ACKs, el checksum del buffer
da perfecto... y la pantalla **no cambia ni un píxel**.

**Fix:** llamar `display.clearDisplay()` antes de llenar el buffer — su memset
es despreciable y marca la pantalla completa como sucia.

### 2. El stall del driver CDC de macOS

Si escribís el frame completo de una ráfaga, el canal Mac→Arduino se atasca:
el chip USB del Uno drena a 115200 baudios (40× más lento que USB) y el driver
de macOS termina en un estado en el que **solo un replug físico lo revive**.

**Fix:** *pacing* — enviar en chunks de 64 bytes al ritmo de la línea física
(`frame_utils.send_frame()`).

### Bonus: gotchas menores

- Abrir **y cerrar** el puerto serial resetea el Uno (DTR) → esperar 2s tras
  abrir, y mirar la pantalla *mientras* el puerto está abierto.
- El Serial Monitor del Arduino IDE **agarra el puerto solo** → `Resource busy`.
- El `Wire` de AVR no tiene timeout por defecto: un glitch I2C = sketch colgado
  para siempre. `Wire.setWireTimeout(25000, true)` lo evita.

## Estructura

```
arduino/oled_hello/      Hola mundo: verifica cableado y dirección I2C
arduino/oled_receiver/   Receptor de frames serial → OLED
python/frame_utils.py    Empaquetado 1-bit + serial (pacing, ACK)
python/send_test_pattern.py  Patrón de diagnóstico
python/mirror.py         El espejo en vivo
```

## Roadmap

- [ ] MediaPipe: cara detectada y auto-encuadrada / malla facial dibujada
- [ ] 500000 baudios (0% de error en el Uno) → ~20 fps
- [ ] Modos alternativos: bordes con Canny, solo landmarks
