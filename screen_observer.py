"""Shared screen observation and dismissal of the game's blank-area hint."""
from functools import lru_cache
from pathlib import Path
import time

import cv2
import numpy as np


@lru_cache(maxsize=1)
def _hint_template():
    path = Path(__file__).parent / 'assets/login/promo_dismiss.png'
    if not path.is_file():
        return None
    return cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), cv2.IMREAD_GRAYSCALE)


def has_dismiss_hint(png):
    template = _hint_template()
    if template is None:
        return False
    image = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return False
    height, width = image.shape[:2]
    if not 1.65 <= width / height <= 2.5:
        return False
    image = cv2.resize(image, (1920, 1080), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(image[750:1080], cv2.COLOR_BGR2GRAY)
    scores = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, (x, y) = cv2.minMaxLoc(scores)
    h, w = template.shape
    return bool(score >= .92 and gray[y:y+h, x:x+w].mean() >= template.mean() * .78)


def capture_screen(adb, serial, runner, *, sleeper=time.sleep, max_dismissals=5,
                   checkpoint=lambda: None, progress=lambda message: None):
    for attempt in range(max_dismissals + 1):
        checkpoint()
        png = runner(adb, '-s', serial, 'exec-out', 'screencap', '-p', timeout=30)
        if not has_dismiss_hint(png):
            return png
        if attempt == max_dismissals:
            raise ValueError('Bảng có hướng dẫn nhấn vùng trống chưa đóng sau khi bấm giữa màn hình.')
        image = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
        height, width = image.shape[:2]
        checkpoint()
        progress('Đóng bảng hướng dẫn: nhấp giữa màn hình để tắt…')
        runner(adb, '-s', serial, 'shell', 'input', 'tap', str(width // 2), str(height // 2))
        sleeper(.5)
