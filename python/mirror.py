"""Modo clasico: espejo en vivo con dithering Floyd-Steinberg.

Camara -> grises 128x64 -> contraste -> dithering FS -> OLED.

Uso:
    python mirror.py --port /dev/cu.usbmodemXXXX [--baud 500000] [--no-flip]
"""

import cv2
import numpy as np
from PIL import Image

import runner


def main() -> None:
    args = runner.parse_args(__doc__)

    def to_mono(frame_bgr: np.ndarray) -> np.ndarray:
        gray = runner.gray_128x64(frame_bgr, flip=not args.no_flip)
        # Estirar contraste: en 1-bit la escena plana desaparece.
        gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
        # Floyd-Steinberg (Pillow convert('1') lo aplica por defecto).
        return np.asarray(Image.fromarray(gray).convert("1"), dtype=np.uint8)

    runner.run(to_mono, args)


if __name__ == "__main__":
    main()
