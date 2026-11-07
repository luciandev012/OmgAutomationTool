"""Shared screen observation and dismissal of the game's blank-area hint."""
from functools import lru_cache
from pathlib import Path
from screen_watchdog import ScreenWatchdog
from runtime_policy import no_step_delay

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


def capture_screen(adb, serial, runner, *, sleeper=no_step_delay, max_dismissals=None,
                   checkpoint=lambda: None, progress=lambda message: None, dismiss_hints=True,
                   watchdog=None):
    monitor = watchdog or ScreenWatchdog()
    attempt = 0
    hint_started = None
    while True:
        checkpoint()
        try:
            png = runner(adb, '-s', serial, 'exec-out', 'screencap', '-p', timeout=30)
        except InterruptedError:
            raise
        except Exception:
            if watchdog is None:
                raise
            monitor.check()
            continue
        monitor.observe(png)
        if not dismiss_hints or not has_dismiss_hint(png):
            return png
        if hint_started is None:
            hint_started = monitor.clock()
        elif monitor.clock() - hint_started >= monitor.timeout:
            # Animated artwork behind a stuck overlay must not mask the stall.
            from screen_watchdog import ScreenStalledError
            raise ScreenStalledError('Thông báo nhấp vùng trống vẫn còn sau 120 giây.')
        if max_dismissals is not None and attempt >= max_dismissals:
            raise ValueError('Bảng có hướng dẫn nhấn vùng trống chưa đóng sau khi bấm vùng trống phía dưới.')
        image = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
        height, width = image.shape[:2]
        checkpoint()
        progress('Đóng bảng hướng dẫn: nhấp vùng trống phía dưới rồi kiểm tra lại…')
        runner(adb, '-s', serial, 'shell', 'input', 'tap', str(width // 2), str(round(height * .974)))
        attempt += 1
