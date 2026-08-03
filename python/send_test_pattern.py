"""Herramienta de diagnostico: envia un patron de prueba fijo a la OLED.

Verifica el camino completo: pack -> header -> serial -> receptor -> buffer -> pantalla.
El patron (marco + cruz diagonal + damero en una esquina) permite ver a simple
vista si hay bytes corridos, ejes invertidos o desincronizacion.

Uso:
    python send_test_pattern.py --port /dev/cu.usbmodemXXXX [--baud 115200]
"""

import argparse
import time

import numpy as np

from frame_utils import HEIGHT, WIDTH, open_serial, send_frame


def build_pattern() -> np.ndarray:
    img = np.zeros((HEIGHT, WIDTH), dtype=np.uint8)
    # Marco de 1px en el borde.
    img[0, :] = 1
    img[-1, :] = 1
    img[:, 0] = 1
    img[:, -1] = 1
    # Cruz diagonal (X) de esquina a esquina.
    xs = np.arange(WIDTH)
    ys = (xs * (HEIGHT - 1) // (WIDTH - 1)).astype(int)
    img[ys, xs] = 1
    img[HEIGHT - 1 - ys, xs] = 1
    # Damero 8x8 en la esquina superior izquierda (referencia de orientacion).
    yy, xx = np.mgrid[0:16, 0:16]
    img[0:16, 0:16] = ((yy // 2 + xx // 2) % 2).astype(np.uint8)
    return img


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True, help="puerto serial del Uno")
    ap.add_argument("--baud", type=int, default=115200)
    args = ap.parse_args()

    pattern = build_pattern()
    ser = open_serial(args.port, args.baud)
    print(f"Enviando patron a {args.port} @ {args.baud}. Ctrl-C para cortar.")

    frames = 0
    misses = 0
    t0 = time.time()
    try:
        while True:
            # send_frame hace pacing y espera el ACK del Uno: se auto-regula.
            if send_frame(ser, pattern):
                frames += 1
            else:
                misses += 1
                print(f"\nsin ACK (total {misses}) - reintento")
            if frames and frames % 20 == 0:
                fps = frames / (time.time() - t0)
                print(f"\r{frames} frames, {fps:.1f} fps, {misses} sin ACK", end="", flush=True)
    except KeyboardInterrupt:
        print("\nCortado.")
    finally:
        ser.close()


if __name__ == "__main__":
    main()
