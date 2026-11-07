"""Per-worker screen inactivity detection; no sleeps and no credential storage."""
import time
import cv2
import numpy as np


class ScreenStalledError(RuntimeError):
    pass


class ScreenWatchdog:
    def __init__(self, timeout=120, clock=time.monotonic):
        self.timeout, self.clock = timeout, clock
        self.reset()

    def reset(self):
        self.anchor = None
        self.changed_at = self.clock()

    def check(self):
        if self.clock() - self.changed_at >= self.timeout:
            raise ScreenStalledError('Màn hình không thay đổi/không lấy được ảnh trong 120 giây.')

    def observe(self, png):
        image = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_GRAYSCALE)
        if image is None:
            self.check()
            raise ValueError('Không đọc được ảnh ADB.')
        # Compare against the last meaningful frame, not the preceding frame:
        # small incremental changes must not accumulate unnoticed forever.
        small = cv2.resize(image, (160, 90), interpolation=cv2.INTER_AREA)
        small = cv2.GaussianBlur(small, (3, 3), 0)
        if self.anchor is None or np.mean(cv2.absdiff(small, self.anchor) > 10) >= .01:
            self.anchor = small
            self.changed_at = self.clock()
        self.check()
