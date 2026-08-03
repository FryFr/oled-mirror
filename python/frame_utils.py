"""Utilidades de frame para oled-mirror.

Convierte una imagen monocroma 64x128 al formato de buffer de pages del
SH1106/SSD1306 y la envia por serial con header magico, pacing y ACK.

Formato del buffer SSD1306 (1024 bytes):
  - 8 "pages" de 128 columnas cada una.
  - byte[page*128 + x] contiene 8 pixeles verticales de la columna x.
  - bit (y % 8) = fila dentro de la page; bit 0 = fila superior de la page.
  - pixel encendido (blanco) = bit en 1.
"""

import time

import numpy as np
import serial

WIDTH = 128
HEIGHT = 64
FRAME_BYTES = 1024
HEADER = bytes([0xAA, 0x55])

# Pacing: el driver CDC de macOS se atasca si se le dispara el frame entero de
# una rafaga (el 16u2 del Uno drena a baud rate, mucho mas lento que USB).
# Se envia en chunks al ritmo de la linea fisica. Verificado en hardware.
# 128 funciona estable a 500000; si volves a 115200 y ves perdidas, baja a 64.
CHUNK = 128

# Pesos de bit por fila-dentro-de-page (y % 8).
_WEIGHTS = (1 << np.arange(8)).astype(np.uint8)


def pack_ssd1306(mono: np.ndarray) -> bytes:
    """Empaqueta una imagen (64,128) al buffer SSD1306 de 1024 bytes.

    Cualquier valor != 0 se considera pixel encendido.
    """
    on = (np.asarray(mono) > 0).astype(np.uint8)  # (64,128)
    if on.shape != (HEIGHT, WIDTH):
        raise ValueError(f"esperaba {(HEIGHT, WIDTH)}, recibi {on.shape}")
    pages = on.reshape(8, 8, WIDTH)               # (page, bit_en_page, x)
    buf = (pages * _WEIGHTS[None, :, None]).sum(axis=1).astype(np.uint8)  # (8,128)
    return buf.reshape(-1).tobytes()


def open_serial(port: str, baud: int = 115200) -> serial.Serial:
    """Abre el puerto y espera 2s el reset del Uno (DTR) antes de enviar."""
    ser = serial.Serial(port, baud, timeout=1, write_timeout=2)
    time.sleep(2.0)          # el Uno se resetea al abrir el puerto (DTR)
    ser.reset_input_buffer()
    return ser


def send_frame(ser: serial.Serial, mono: np.ndarray, wait_ack: bool = True) -> bool:
    """Envia un frame con pacing y espera el ACK del Uno.

    Devuelve True si llego el ACK ('K' ok / 'T' hubo timeout de Wire pero el
    receptor sigue vivo). False = sin respuesta (receptor caido o desync).
    """
    data = HEADER + pack_ssd1306(mono)
    chunk_s = CHUNK * 10 / ser.baudrate      # 10 bits por byte en la linea
    # Pacing contra cronograma absoluto: el overshoot de time.sleep (1-2ms en
    # macOS) se absorbe en el siguiente deadline en vez de acumularse.
    t_start = time.monotonic()
    for n, i in enumerate(range(0, len(data), CHUNK), start=1):
        ser.write(data[i : i + CHUNK])
        wait = t_start + n * chunk_s - time.monotonic()
        if wait > 0:
            time.sleep(wait)
    if not wait_ack:
        return True
    return read_ack(ser)


def read_ack(ser: serial.Serial) -> bool:
    """Espera el ACK de un frame ya enviado (para pipelining envio/captura)."""
    return ser.read(1) in (b"K", b"T")
