"""Espejo en vivo: camara -> OLED.

OpenCV captura -> grises -> center-crop 2:1 -> resize 128x64 ->
dithering Floyd-Steinberg (Pillow) -> serial con pacing + ACK.

Uso:
    python mirror.py --port /dev/cu.usbmodemXXXX [--baud 115200] [--no-flip]

La primera vez macOS pide permiso de camara para la terminal.
"""

import argparse
import time

import cv2
import numpy as np
import serial
from PIL import Image

from frame_utils import HEIGHT, WIDTH, open_serial, send_frame


def to_oled(frame_bgr: np.ndarray, flip: bool) -> np.ndarray:
    """BGR de camara -> imagen 1-bit (64,128) lista para empaquetar."""
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    if flip:
        gray = cv2.flip(gray, 1)          # espejo horizontal

    # Center-crop a aspecto 2:1 (128x64) para no deformar.
    h, w = gray.shape
    target_w = min(w, h * 2)
    target_h = target_w // 2
    x0 = (w - target_w) // 2
    y0 = (h - target_h) // 2
    gray = gray[y0 : y0 + target_h, x0 : x0 + target_w]

    gray = cv2.resize(gray, (WIDTH, HEIGHT), interpolation=cv2.INTER_AREA)

    # Estirar contraste: en 1-bit la escena plana desaparece.
    gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)

    # Floyd-Steinberg (Pillow convert('1') lo aplica por defecto).
    mono = Image.fromarray(gray).convert("1")
    return np.asarray(mono, dtype=np.uint8)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--no-flip", action="store_true", help="sin espejado horizontal")
    args = ap.parse_args()

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        raise SystemExit("No pude abrir la camara (¿permiso de macOS?)")
    # Resolucion baja: igual terminamos en 128x64 y captura mas rapido.
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    ser = open_serial(args.port, args.baud)
    print(f"Espejo en vivo -> {args.port} @ {args.baud}. Ctrl-C para cortar.")

    frames = 0
    misses = 0
    t0 = time.time()
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("\nframe de camara perdido")
                continue
            mono = to_oled(frame, flip=not args.no_flip)
            try:
                if send_frame(ser, mono):
                    frames += 1
                else:
                    misses += 1
            except (serial.SerialException, OSError):
                # Microcorte del USB (adaptador flojo): reconectar solo.
                print("\nserial caido - reconectando...", flush=True)
                try:
                    ser.close()
                except Exception:
                    pass
                while True:
                    time.sleep(1.0)
                    try:
                        ser = open_serial(args.port, args.baud)
                        print("reconectado.", flush=True)
                        break
                    except (serial.SerialException, OSError):
                        continue
            if frames and frames % 20 == 0:
                fps = frames / (time.time() - t0)
                print(f"\r{frames} frames, {fps:.1f} fps, {misses} sin ACK", end="", flush=True)
    except KeyboardInterrupt:
        print("\nCortado.")
    finally:
        cap.release()
        ser.close()


if __name__ == "__main__":
    main()
