import io
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from telegram_bot.services.image_service import decode_image


@lru_cache(maxsize=1)
def cascade_xml() -> str:
    return (Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml").read_text(
        encoding="utf-8"
    )


def load_detector():
    # OpenCV's native filename loader can fail on Unicode Windows paths.
    storage = cv2.FileStorage(cascade_xml(), cv2.FILE_STORAGE_READ | cv2.FILE_STORAGE_MEMORY)
    detector = cv2.CascadeClassifier()
    try:
        detector.read(storage.getFirstTopLevelNode())
    finally:
        storage.release()
    if detector.empty():
        raise RuntimeError("OpenCV face cascade is missing")
    return detector


def censor_regions(rgba: np.ndarray, faces, mode: str) -> np.ndarray:
    if mode not in {"pixelate", "blur"}:
        raise ValueError("Unknown censorship mode")
    result = rgba.copy()
    height, width = result.shape[:2]
    for x, y, w, h in faces:
        x0, y0 = max(0, int(x)), max(0, int(y))
        x1, y1 = min(width, int(x + w)), min(height, int(y + h))
        if x1 <= x0 or y1 <= y0:
            continue
        roi = result[y0:y1, x0:x1, :3]
        if mode == "blur":
            hidden = cv2.GaussianBlur(roi, (51, 51), sigmaX=0)
        else:
            tiny = cv2.resize(
                roi,
                (max(1, (x1 - x0) // 20), max(1, (y1 - y0) // 20)),
                interpolation=cv2.INTER_AREA,
            )
            hidden = cv2.resize(tiny, (x1 - x0, y1 - y0), interpolation=cv2.INTER_NEAREST)
        result[y0:y1, x0:x1, :3] = hidden
    return result


class FaceCensor:
    def process(self, data: bytes, mode: str, max_pixels: int) -> tuple[bytes, int] | None:
        with decode_image(data, max_pixels) as image:
            rgba = np.array(image)
        # One classifier per CPU task; shared OpenCV classifiers are not thread safe.
        detector = load_detector()
        rgb = rgba[:, :, :3]
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        scale = min(1.0, 1600 / max(gray.shape))
        preview = cv2.resize(gray, None, fx=scale, fy=scale) if scale < 1 else gray
        detected = detector.detectMultiScale(
            cv2.equalizeHist(preview), scaleFactor=1.1, minNeighbors=5, minSize=(24, 24)
        )
        if len(detected) == 0:
            return None
        faces = np.rint(np.asarray(detected) / scale).astype(int)
        censored = censor_regions(rgba, faces, mode)
        with Image.fromarray(censored) as output, io.BytesIO() as buffer:
            # No EXIF, filenames, location or other source metadata are copied.
            output.save(buffer, format="PNG")
            return buffer.getvalue(), len(faces)
