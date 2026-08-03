"""Modo bordes: solo los contornos de la escena (Canny), estetica "Tron".

Los bordes ya son 1-bit por naturaleza: lineas blancas finas sobre negro,
ideal para OLED. Sin dithering.

Uso:
    python mirror_canny.py --port /dev/cu.usbmodemXXXX [--baud 500000]
"""

import cv2
import numpy as np

import runner


def main() -> None:
    args = runner.parse_args(__doc__)

    def to_mono(frame_bgr: np.ndarray) -> np.ndarray:
        gray = runner.gray_128x64(frame_bgr, flip=not args.no_flip)
        # Blur suave antes de Canny: sin el, el ruido del sensor se vuelve nieve.
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        edges = cv2.Canny(gray, 60, 130)
        return (edges > 0).astype(np.uint8)

    runner.run(to_mono, args)


if __name__ == "__main__":
    main()
