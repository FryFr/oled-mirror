"""Runner comun para los modos del espejo.

Cada modo define una funcion `to_mono(frame_bgr) -> np.ndarray (64,128) 1-bit`
y llama a `run(to_mono)`. El runner pone el resto: captura en hilo (sin
bloquear en la camara), pipeline envio/procesamiento/ACK, auto-reconexion
serial y contador de fps.
"""

import argparse
import threading
import time

import cv2
import numpy as np
import serial

from frame_utils import HEIGHT, WIDTH, open_serial, read_ack, send_frame


class CameraGrabber:
    """Hilo que captura continuamente y guarda solo el frame mas reciente.

    cap.read() bloquea hasta el proximo frame de camara (33ms a 30fps); si el
    loop principal lo llamara directo, quedaria cuantizado a multiplos de ese
    periodo. Con el hilo, el loop toma siempre el ultimo frame sin bloquear.
    """

    def __init__(self, cap: cv2.VideoCapture):
        self._cap = cap
        self._frame: np.ndarray | None = None
        self._lock = threading.Lock()
        self.running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self) -> None:
        while self.running:
            ok, frame = self._cap.read()
            if ok:
                with self._lock:
                    self._frame = frame

    def latest(self) -> np.ndarray | None:
        with self._lock:
            return None if self._frame is None else self._frame


def gray_128x64(frame_bgr: np.ndarray, flip: bool = True) -> np.ndarray:
    """BGR de camara -> grises 128x64 sin deformar (espejado por defecto)."""
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    if flip:
        gray = cv2.flip(gray, 1)
    h, w = gray.shape
    target_w = min(w, h * 2)          # center-crop a aspecto 2:1
    target_h = target_w // 2
    x0 = (w - target_w) // 2
    y0 = (h - target_h) // 2
    gray = gray[y0 : y0 + target_h, x0 : x0 + target_w]
    return cv2.resize(gray, (WIDTH, HEIGHT), interpolation=cv2.INTER_AREA)


def parse_args(description: str) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--port", required=True, help="puerto serial del Uno")
    ap.add_argument("--baud", type=int, default=500000)
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--no-flip", action="store_true", help="sin espejado horizontal")
    return ap.parse_args()


def run(to_mono, args: argparse.Namespace) -> None:
    """Loop principal: captura -> to_mono(frame) -> serial con pipeline y ACK."""
    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        raise SystemExit("No pude abrir la camara (¿permiso de macOS?)")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    ser = open_serial(args.port, args.baud)
    print(f"-> {args.port} @ {args.baud}. Ctrl-C para cortar.")

    grabber = CameraGrabber(cap)
    while grabber.latest() is None:
        time.sleep(0.05)

    frames = 0
    misses = 0
    t0 = time.time()
    mono = None
    try:
        while True:
            try:
                # Pipeline: enviar sin esperar ACK, procesar el proximo frame
                # mientras el Uno dibuja, y recien ahi cobrar el ACK.
                if mono is not None:
                    send_frame(ser, mono, wait_ack=False)
                mono_next = to_mono(grabber.latest())
                if mono is not None:
                    if read_ack(ser):
                        frames += 1
                    else:
                        misses += 1
                mono = mono_next
            except (serial.SerialException, OSError):
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
        grabber.running = False
        time.sleep(0.1)
        cap.release()
        ser.close()
