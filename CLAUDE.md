# oled-mirror

Cámara de la Mac → procesamiento en Python (OpenCV + MediaPipe) → conversión a
1-bit con dithering Floyd-Steinberg → envío por serial → Arduino Uno → OLED
**GME12864** (controlador **SH1106**, 128×64, I2C) dibujada en vivo.

## Hardware

- **Placa:** Arduino Uno (`arduino:avr:uno`). SRAM 2KB, Flash 32KB.
- **OLED:** GME12864 — controlador **SH1106** (¡NO SSD1306!), 128×64, I2C.
  Librería **Adafruit SH110X**, clase `Adafruit_SH1106G`, `begin(0x3C, true)`,
  color `SH110X_WHITE`. Dirección `0x3C` (alt `0x3D`). 3.3–5V tolerante.
  Verificado en hardware: con SSD1306 no muestra nada; con SH1106 anda.
- **Cableado I2C:** SDA → A4, SCL → A5, VCC → 5V, GND → GND.
- **I2C a 400 kHz:** `Wire.setClock(400000)`.

## Puerto serial

- **Puerto:** `/dev/cu.usbmodem141011` (Arduino UNO detectado). Puede cambiar el sufijo entre reconexiones → reconfirmar con `arduino-cli board list`.
- **Baudios:** **500000** (0% de error en el Uno; 115200 tiene ~3.5%). El receptor
  y los scripts Python ya lo usan por defecto.
- **Reset por DTR:** al abrir el puerto con pyserial el Uno se resetea. **Esperar 2s antes de enviar** (`open_serial()` en `python/frame_utils.py` ya lo hace).

## Protocolo de frame

```
Mac → Uno:  [0xAA][0x55] + 1024 bytes  (formato buffer de pages)
Uno → Mac:  1 byte de ACK: 'K' ok · 'N' OLED no responde ping I2C · 'T' Wire timeout
```

- Header mágico de 2 bytes para sincronización. El Uno solo busca el header en
  los límites de frame; ante pérdida de un byte, eventualmente re-sincroniza.
- **ACK = control de flujo:** Python espera el ACK antes del próximo frame.
  El ping I2C del ACK detecta cable suelto (un NACK **no** dispara el Wire timeout).
- **1024 bytes = 8 pages × 128 columnas.** `byte[page*128 + x]` = 8 píxeles
  verticales; bit `(y % 8)` = fila dentro de la page (bit 0 = arriba).
  Empaquetado en `frame_utils.pack_ssd1306()` (verificado con asserts + checksum
  en hardware).
- Rendimiento medido: **16 fps estables** a 500000 con pipeline (envío sin
  esperar ACK → procesar el próximo frame → cobrar ACK) y pacing por cronograma
  absoluto. Techo práctico: el Wire de AVR trocea cada página en transacciones
  I2C de 32 bytes → volcado ~35ms. No mandar serial durante display() (gatillo
  del stall CDC).

## Gotchas duros (verificados en hardware, costaron sangre)

1. **Dirty window de Adafruit SH110X:** a diferencia de SSD1306, `display()`
   SOLO transmite la región marcada "sucia" por funciones GFX y luego la resetea.
   Escribir `getBuffer()` directo no marca nada → `display()` transmite CERO
   bytes con éxito aparente. **Fix:** `clearDisplay()` (marca todo sucio) antes
   de llenar el buffer con el frame.
2. **Stall del driver CDC de macOS:** enviar el frame de una ráfaga atasca el
   canal Mac→16u2 (write timeout; solo revive con replug físico del USB).
   **Fix:** pacing — chunks de 64 bytes al ritmo de línea (`send_frame()`).
   Agravante: adaptador USB-A→C (conviene cable USB-C→USB-B directo).
3. **Sesiones pyserial que mueren en write timeout envenenan el próximo upload**
   de avrdude ("unable to open port"/"not in sync"). Cerrar el puerto limpio
   (SIGINT, `ser.close()`) lo evita; si pasa, replug físico.
4. **Cerrar el puerto también resetea el Uno (DTR)** → la pantalla vuelve al
   estado del `setup()`. Mirar la OLED **mientras** el puerto está abierto.
5. **El Arduino IDE agarra el puerto solo** (su serial monitor). Si algo falla
   con "Resource busy": `lsof /dev/cu.usbmodem*` y cerrar el IDE.
6. **Wire de AVR no tiene timeout por defecto** → `Wire.setWireTimeout(25000, true)`
   o un glitch I2C cuelga el sketch para siempre.

## Restricción de memoria (CLAVE)

El Uno tiene 2KB SRAM. El buffer de la SSD1306 (1024 bytes) se hace con `malloc`
en `display.begin()` → sale del heap, dejando ~500 bytes para stack. **Por eso el
receptor escribe los bytes serial DIRECTO en `display.getBuffer()`** — sin buffers
intermedios, sin `String`. (Compilado: 519 bytes globales, 1529 libres.)

## Comandos

```bash
# Compilar
arduino-cli compile --fqbn arduino:avr:uno arduino/oled_hello
arduino-cli compile --fqbn arduino:avr:uno arduino/oled_receiver

# Subir (reemplazar PORT)
arduino-cli upload  --fqbn arduino:avr:uno -p PORT arduino/oled_receiver

# Monitor serial
arduino-cli monitor -p PORT -c baudrate=115200

# Detectar placa
arduino-cli board list

# Python (venv 3.12 — MediaPipe NO tiene wheels para 3.14)
./venv/bin/python python/send_test_pattern.py --port PORT
```

## Estructura

```
arduino/oled_hello/      Hito 1 — hola mundo OLED (verifica cableado + I2C)
arduino/oled_receiver/   Hito 2 — receptor de frames serial
python/frame_utils.py    pack SSD1306 + serial (header + 2s DTR)
python/send_test_pattern.py  Hito 2 — patrón de prueba fijo
venv/                    Python 3.12 (opencv, mediapipe, pyserial, numpy, pillow)
```

## Estado

Todos los hitos completos. Modos disponibles (comparten `python/runner.py`):
- `mirror.py` — clásico con dithering FS
- `mirror_canny.py` — bordes Canny
- `mirror_face.py` — contornos faciales MediaPipe Tasks API (FaceLandmarker,
  modelo se auto-descarga a `python/models/`), suavizado EMA alpha 0.45.

OJO: mediapipe 1.0 **eliminó `mp.solutions`** — solo existe la Tasks API
(`mediapipe.tasks.python.vision`). Contornos en
`vision.FaceLandmarksConnections.FACE_LANDMARKS_CONTOURS` (124 pares .start/.end).

## Cámara en macOS

- El permiso es por-app: dárselo a **VS Code** (host de la terminal) en
  Ajustes → Privacidad → Cámara. El proceso además no puede correr sandboxeado.
- Error típico sin permiso: `not authorized to capture video` /
  `Failed list devices for backend avfoundation`.

## Aprendizajes de MediaPipe (proyectos previos en TouchDesigner)

> Vienen del plugin "MediaPipe for TouchDesigner". La API difiere de la librería
> Python, pero los conceptos transfieren.

- **Coordenadas normalizadas 0–1.** En TD el origen era abajo-izquierda; en
  **Python MediaPipe el origen es arriba-izquierda**. Ojo al mapear a la OLED:
  invertir Y o espejar la cámara sin querer **descuadra** todo el encuadre.
- **Suavizado temporal obligatorio.** Los landmarks tiemblan; en TD se usó Lag
  0.06–0.08. En una pantalla de 64px de alto el jitter se nota muchísimo → aplicar
  filtro temporal (EMA) a las coordenadas antes de dibujar.
- **Presencia + detección de flanco.** Actuar solo cuando la detección es
  confiable; contar gestos por flanco de subida, no en cada frame.
- **Umbral de pinch** ~0.05–0.06 (normalizado), si algún día se usan gestos.
- **Permiso de cámara de macOS es por-app.** La primera vez que Python abra la
  webcam, macOS pide permiso; puede requerir reiniciar la terminal/proceso.
- **MediaPipe suelta detecciones** cuando dos manos/objetos se juntan o salen de
  cuadro → diseñar para que la ausencia no rompa el dibujo (fallback a último
  frame o a cámara cruda).
```
