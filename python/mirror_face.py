"""Modo cara: contornos faciales con MediaPipe (ovalo, cejas, ojos, labios).

Dibuja solo los contornos de FaceLandmarker — la malla completa (tesselation)
seria sopa de pixeles en 128x64. Aplica suavizado EMA a los landmarks (el
jitter de MediaPipe se nota muchisimo en 64px de alto) y solo dibuja cuando
hay cara detectada.

El modelo (~3.7MB) se descarga solo la primera vez a models/.

Uso:
    python mirror_face.py --port /dev/cu.usbmodemXXXX [--baud 500000]
"""

import pathlib
import time
import urllib.request

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python import vision

import runner
from frame_utils import HEIGHT, WIDTH

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
MODEL_PATH = pathlib.Path(__file__).parent / "models" / "face_landmarker.task"

# Suavizado temporal de landmarks (equivalente al Lag ~0.08 de TouchDesigner).
# alpha mas bajo = mas suave pero mas "lag" visual.
EMA_ALPHA = 0.45

# Contornos: ovalo + cejas + ojos + labios (pares de indices de landmarks).
CONTOURS = [
    (c.start, c.end)
    for c in vision.FaceLandmarksConnections.FACE_LANDMARKS_CONTOURS
]


def ensure_model() -> None:
    if MODEL_PATH.exists():
        return
    MODEL_PATH.parent.mkdir(exist_ok=True)
    print(f"Descargando modelo a {MODEL_PATH} ...")
    urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    print("Modelo descargado.")


def main() -> None:
    args = runner.parse_args(__doc__)
    ensure_model()

    landmarker = vision.FaceLandmarker.create_from_options(
        vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(MODEL_PATH)),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
        )
    )

    smoothed: np.ndarray | None = None  # (478, 2) en pixeles OLED
    t_start = time.monotonic()

    def to_mono(frame_bgr: np.ndarray) -> np.ndarray:
        nonlocal smoothed
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        if not args.no_flip:
            rgb = cv2.flip(rgb, 1)

        ts_ms = int((time.monotonic() - t_start) * 1000)
        result = landmarker.detect_for_video(
            mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts_ms
        )

        canvas = np.zeros((HEIGHT, WIDTH), dtype=np.uint8)
        if not result.face_landmarks:
            # Presencia: sin cara no se dibuja basura; se suelta el suavizado
            # para no "arrastrar" la cara vieja cuando reaparezca en otro lado.
            smoothed = None
            return canvas

        # Coordenadas normalizadas 0-1, origen ARRIBA-izquierda (a diferencia
        # de TouchDesigner, que era abajo-izquierda). Mapeo directo a OLED.
        lm = result.face_landmarks[0]
        pts = np.array([(p.x * (WIDTH - 1), p.y * (HEIGHT - 1)) for p in lm])

        # EMA: suaviza el jitter de los landmarks.
        smoothed = pts if smoothed is None else (
            EMA_ALPHA * pts + (1 - EMA_ALPHA) * smoothed
        )

        pix = smoothed.round().astype(int)
        for a, b in CONTOURS:
            cv2.line(canvas, tuple(pix[a]), tuple(pix[b]), 1, 1)
        return canvas

    runner.run(to_mono, args)


if __name__ == "__main__":
    main()
