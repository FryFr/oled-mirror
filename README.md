# oled-mirror 🪞

> Un espejo de **1024 píxeles**: tu cámara te captura, Python procesa el video
> en tiempo real y te dibuja en vivo sobre una pantallita OLED de 128×64
> conectada a un Arduino Uno.

📸 _[Fotos y video demo próximamente]_

---

## ¿Qué es esto?

Es un proyecto de **visión artificial** que conecta dos mundos que normalmente
no se hablan: el procesamiento de video moderno (OpenCV, MediaPipe) y un
microcontrolador de 8 bits con **2KB de RAM**.

La idea en una frase: la Mac hace el trabajo pesado (capturar, procesar y
reducir cada frame a blanco y negro puro), y el Arduino solo recibe 1024 bytes
por el cable USB y los dibuja. El resultado: te mirás en una pantalla del
tamaño de una estampilla, a **16 cuadros por segundo**.

No necesitás experiencia previa con Arduino ni con visión artificial para
armarlo — la sección [Armalo vos](#armalo-vos) te lleva paso a paso.

## Stack

| Tecnología | Rol en el proyecto |
|---|---|
| **Python 3.12** | Orquesta todo el lado Mac |
| **OpenCV** | Captura de cámara, escala de grises, resize, detección de bordes |
| **MediaPipe** (Tasks API) | Detección de landmarks faciales (modo cara) |
| **Pillow** | Dithering Floyd-Steinberg (video → 1-bit) |
| **pySerial** | Envío de frames por USB con control de flujo propio |
| **Arduino Uno** (C++) | Recibe frames y los vuelca a la pantalla por I2C |
| **Adafruit SH110X** | Driver de la OLED |
| **arduino-cli** | Compilación y subida de sketches desde la terminal |

## Los 3 modos

| Modo | Archivo | Qué ves |
|---|---|---|
| 🪞 **Clásico** | `python/mirror.py` | Tu imagen real, convertida a puntitos blancos y negros (dithering) |
| ⚡ **Bordes** | `python/mirror_canny.py` | Solo los contornos de la escena, estética "Tron" |
| 🙂 **Cara** | `python/mirror_face.py` | Tu cara como dibujo de líneas: óvalo, cejas, ojos y labios siguiéndote en vivo |

Los tres comparten el mismo motor (`python/runner.py`). **Crear tu propio modo
es escribir una función de ~10 líneas** que reciba un frame de cámara y
devuelva una imagen de 128×64 en blanco y negro — el runner hace el resto.

## Cómo funciona por dentro

```
┌─────────────────────── Mac (Python) ───────────────────────┐
│ OpenCV captura → grises → espejo → crop 2:1 → 128×64       │
│ → procesamiento del modo (dithering / Canny / MediaPipe)   │
│ → serial: [0xAA][0x55] + 1024 bytes (con pacing)           │
└──────────────────────────┬─────────────────────────────────┘
                           │ USB serial 500000 baudios
┌──────────────────────────▼─────────────────────────────────┐
│ Arduino Uno: busca header → escribe los 1024 bytes DIRECTO │
│ en el buffer de la librería → display() → ACK              │
└──────────────────────────┬─────────────────────────────────┘
                           │ I2C 400kHz
                    OLED SH1106 128×64
```

¿Por qué 1024 bytes? La pantalla tiene 128×64 = 8192 píxeles, y cada píxel es
1 bit (encendido o apagado): 8192 / 8 = **1024 bytes por frame completo**.
Justo la mitad de la RAM total del Uno — por eso el sketch escribe los bytes
recibidos directo sobre el buffer de la librería, sin copias intermedias.

## Hardware

| Componente | Detalle |
|---|---|
| Arduino Uno | Cualquier Uno (o clon) sirve |
| OLED GME12864 | Controlador **SH1106** (¡ojo, no SSD1306!), I2C, dirección `0x3C` |
| 4 cables dupont | Hembra-macho para conectar la OLED |
| Cable USB | El USB-B clásico del Uno |

**Conexión de la OLED** (4 cables):

```
OLED          Arduino Uno
────          ───────────
VCC   ──────  5V
GND   ──────  GND
SDA   ──────  A4
SCL   ──────  A5
```

## Armalo vos

### 1. Instalar las herramientas (una sola vez)

```bash
# arduino-cli: compila y sube sketches sin abrir el IDE
brew install arduino-cli
arduino-cli config init
arduino-cli core install arduino:avr
arduino-cli lib install "Adafruit SH110X"

# Entorno de Python (3.12: MediaPipe aún no soporta 3.14)
python3.12 -m venv venv
./venv/bin/pip install -r requirements.txt
```

### 2. Encontrar el puerto del Arduino

Conectá el Uno por USB y corré:

```bash
arduino-cli board list
```

Vas a ver algo como `/dev/cu.usbmodem141011  ...  Arduino UNO`. Ese es tu
puerto — usalo en los comandos que siguen en lugar de `<PUERTO>`.

### 3. Probar la pantalla

```bash
arduino-cli compile --fqbn arduino:avr:uno arduino/oled_hello
arduino-cli upload  --fqbn arduino:avr:uno -p <PUERTO> arduino/oled_hello
```

Si la OLED muestra texto, el cableado está bien. Si queda negra, revisá los
4 cables y la [sección de problemas](#si-algo-no-anda).

### 4. Subir el receptor y encender el espejo

```bash
arduino-cli compile --fqbn arduino:avr:uno arduino/oled_receiver
arduino-cli upload  --fqbn arduino:avr:uno -p <PUERTO> arduino/oled_receiver

# Elegí tu modo:
./venv/bin/python python/mirror.py       --port <PUERTO>   # clásico
./venv/bin/python python/mirror_canny.py --port <PUERTO>   # bordes
./venv/bin/python python/mirror_face.py  --port <PUERTO>   # cara (descarga el modelo la 1ª vez)
```

> **macOS te va a pedir permiso de cámara** para la terminal la primera vez
> (Ajustes → Privacidad y seguridad → Cámara).

## El protocolo serial (para curiosos)

```
Mac → Uno:  [0xAA][0x55] + 1024 bytes  (8 pages × 128 columnas)
Uno → Mac:  1 byte de ACK: 'K' ok · 'N' OLED no responde · 'T' timeout I2C
```

- El **header mágico** (`0xAA 0x55`) permite re-sincronizar si se pierde un byte.
- El **ACK** es control de flujo real: Python no envía el siguiente frame hasta
  que el Uno confirmó el anterior. Además hace un ping I2C a la OLED, así que
  detecta hasta un cable flojo.
- El envío usa **pacing** (chunks de 128 bytes al ritmo de la línea) y
  **pipeline**: mientras el Uno dibuja el frame N, la Mac ya procesa el N+1.

### ¿Por qué 16 fps y no más?

A 500000 baudios el serial tarda ~21ms por frame, pero el volcado I2C a la
pantalla tarda ~35ms: el `Wire` de AVR trocea cada página en transacciones de
32 bytes con overhead de dirección en cada una. Ese es el techo práctico del
stack — y la historia completa de cómo pasamos de 5.9 a 16 fps está en los
commits.

## Los dos bugs que casi nos vuelven locos 🐛

Documentados porque **le van a pasar a cualquiera** que replique esto:

### 1. El dirty window de Adafruit SH110X

A diferencia de `Adafruit_SSD1306`, en la librería SH110X `display()` **solo
transmite la región "sucia"** que fue marcada por funciones GFX (`drawPixel`,
`println`...). Si escribís `getBuffer()` directo, la librería no se entera:
`display()` termina "exitoso", el I2C responde ACKs, el checksum del buffer da
perfecto... y la pantalla **no cambia ni un píxel**.

**Fix:** llamar `display.clearDisplay()` antes de llenar el buffer — su memset
es despreciable y marca la pantalla completa como sucia.

### 2. El stall del driver CDC de macOS

Si escribís el frame completo de una ráfaga, el canal Mac→Arduino se atasca:
el chip USB del Uno drena a baud rate (mucho más lento que USB) y el driver de
macOS termina en un estado en el que **solo un replug físico lo revive**.

**Fix:** *pacing* — enviar en chunks al ritmo de la línea física
(`frame_utils.send_frame()`).

## Si algo no anda

| Síntoma | Causa probable | Solución |
|---|---|---|
| OLED negra con el hola mundo | Cable flojo o dirección I2C | Reencajar los 4 cables; probar `0x3D` |
| `Resource busy` al abrir el puerto | El Arduino IDE tiene el puerto agarrado | Cerrar el IDE (su Serial Monitor lo toma solo) |
| Upload falla con `not in sync` | Canal USB atascado | Desenchufar y enchufar el USB |
| `not authorized to capture video` | Falta permiso de cámara | Ajustes → Privacidad → Cámara → habilitar tu terminal |
| La imagen desaparece al cerrar el script | Es normal: cerrar el puerto resetea el Uno (DTR) | Mirar la OLED mientras el script corre |

## Estructura

```
arduino/oled_hello/          Hola mundo: verifica cableado y dirección I2C
arduino/oled_receiver/       Receptor de frames serial → OLED
python/frame_utils.py        Empaquetado 1-bit + serial (pacing, ACK)
python/runner.py             Motor común: captura en hilo + pipeline + reconexión
python/mirror.py             Modo clásico (dithering Floyd-Steinberg)
python/mirror_canny.py       Modo bordes (Canny)
python/mirror_face.py        Modo cara (MediaPipe FaceLandmarker)
python/send_test_pattern.py  Patrón de diagnóstico del pipeline
requirements.txt             Dependencias de Python
```

## Roadmap

- [x] Espejo en vivo con dithering Floyd-Steinberg
- [x] 500000 baudios + pipeline → **16 fps** (2.7× vs 115200)
- [x] Modo bordes con Canny
- [x] Modo cara con MediaPipe (contornos + suavizado EMA)
- [ ] Cara auto-encuadrada (zoom/centrado siguiendo la detección)
- [ ] Gestos con las manos para cambiar de modo en vivo
