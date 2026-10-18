"""Observe, act and verify the OMG 3Q ZingID login flow."""
from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
ACCOUNT_FILE = ROOT / "account.txt"
CREDENTIAL_FILE = ROOT / "credentials.local.json"
OPTIONS_FILE = ROOT / "login_settings.json"
PACKAGE = "com.gs2.omg"
SIZE = (1920, 1080)


def load_accounts(path: Path = ACCOUNT_FILE) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        raise ValueError(f"Không đọc được {path.name}. Mỗi dòng cần chứa một tên đăng nhập.") from exc
    accounts = []
    for line_number, line in enumerate(lines, 1):
        name = line.strip()
        if not name or name.startswith("#"):
            continue
        if len(name) > 128 or any(ord(c) < 33 or ord(c) > 126 for c in name):
            raise ValueError(f"Tên đăng nhập ở dòng {line_number} không hợp lệ.")
        if name not in accounts:
            accounts.append(name)
    if not accounts:
        raise ValueError("account.txt chưa có tài khoản. Mỗi dòng ghi một tên đăng nhập.")
    return accounts


def load_common_password(path: Path = CREDENTIAL_FILE) -> str:
    if not path.exists():
        return ""
    try:
        password = json.loads(path.read_text(encoding="utf-8-sig")).get("common_password", "")
        if not isinstance(password, str):
            raise ValueError()
        return password
    except (OSError, ValueError):
        raise ValueError(f"Không đọc được mật khẩu chung trong {path.name}.") from None


def load_options() -> dict:
    defaults = {"accept_terms": False, "enter_game": True, "prefer_played_server": True}
    if OPTIONS_FILE.exists():
        data = json.loads(OPTIONS_FILE.read_text(encoding="utf-8"))
        defaults.update({k: v for k, v in data.items() if k in defaults and isinstance(v, bool)})
    return defaults


def save_options(options: dict) -> None:
    OPTIONS_FILE.write_text(json.dumps(options, ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass(frozen=True)
class Match:
    name: str
    x: int
    y: int
    width: int
    height: int
    score: float

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.width // 2, self.y + self.height // 2


@dataclass(frozen=True)
class LoginResult:
    status: str
    message: str
    screenshot: str = ""


class Detector:
    # Restrict searches to the actual UI areas; text on the backdrop must not win.
    REGIONS = {
        "notice_accept": (700, 870, 1200, 1060),
        "zingid": (600, 300, 1320, 700),
        "zingid_form": (600, 180, 1320, 600),
        "submit": (650, 500, 1280, 760),
        "cancel": (1050, 680, 1300, 870),
        "start_game": (650, 800, 1250, 990),
        "switch_account": (1600, 180, 1920, 370),
        "choose_server": (1000, 700, 1360, 880),
        "terms_label": (500, 950, 860, 1050),
        "server_panel": (750, 45, 1180, 160),
        "played_tab": (230, 150, 570, 290),
        "server_card": (580, 160, 1680, 950),
        "lobby_status": (930, 0, 1120, 130),
        "lobby_menu": (0, 700, 1920, 1080),
        "lobby_announcement": (1000, 50, 1800, 300),
        "announcement_confirm": (700, 890, 1230, 1080),
        "promo_dismiss": (650, 980, 1260, 1080),
        "create_character": (0, 0, 1920, 1080),
    }

    def __init__(self, asset_dir: Path | None = None):
        self.templates = {}
        for path in (asset_dir or ROOT / "assets/login").glob("*.png"):
            raw = np.frombuffer(path.read_bytes(), np.uint8)
            image = cv2.imdecode(raw, cv2.IMREAD_GRAYSCALE)
            if image is not None:
                self.templates[path.stem] = image

    @staticmethod
    def decode(png: bytes) -> np.ndarray:
        image = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Không đọc được ảnh màn hình MuMu.")
        if abs(image.shape[1] / image.shape[0] - 16 / 9) > .12:
            raise ValueError("Đặt giả lập ở màn hình ngang tỉ lệ 16:9 để dùng nhận diện đăng nhập.")
        return cv2.resize(image, SIZE, interpolation=cv2.INTER_AREA)

    def find(self, frame: np.ndarray, name: str, threshold: float = .92) -> Match | None:
        template = self.templates.get(name)
        if template is None:
            return None
        x1, y1, x2, y2 = self.REGIONS.get(name, (0, 0, *SIZE))
        roi = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
        if roi.shape[0] < template.shape[0] or roi.shape[1] < template.shape[1]:
            return None
        scores = cv2.matchTemplate(roi, template, cv2.TM_CCOEFF_NORMED)
        _, confidence, _, point = cv2.minMaxLoc(scores)
        if confidence < threshold:
            return None
        return Match(name, point[0] + x1, point[1] + y1,
                     template.shape[1], template.shape[0], confidence)

    def first_played_card(self, frame: np.ndarray) -> Match | None:
        template = self.templates.get("server_card")
        if template is None:
            return None
        x1, y1, x2, y2 = self.REGIONS["server_card"]
        roi = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
        scores = cv2.matchTemplate(roi, template, cv2.TM_CCOEFF_NORMED)
        ys, xs = np.where(scores >= .95)
        if len(xs) == 0:
            return None
        # The collection tab is ordered by the game. Prefer its first visible character.
        candidates = sorted(zip(ys, xs), key=lambda p: (int(p[0]) // 25, int(p[1])))
        y, x = candidates[0]
        return Match("server_card", int(x) + x1, int(y) + y1,
                     template.shape[1], template.shape[0], float(scores[y, x]))

    def unobscured(self, frame: np.ndarray, match: Match) -> bool:
        template = self.templates[match.name]
        patch = cv2.cvtColor(frame[match.y:match.y + match.height,
                                  match.x:match.x + match.width], cv2.COLOR_BGR2GRAY)
        return float(patch.mean()) >= float(template.mean()) * .80

    @staticmethod
    def orange_button(frame: np.ndarray, match: Match) -> bool:
        x, y = match.center
        region = frame[max(0, y - 25):y + 25, max(0, x - 60):x + 60].astype(np.int16)
        b, g, r = region[:, :, 0], region[:, :, 1], region[:, :, 2]
        return np.mean((r > 185) & (g > 55) & (g < 190) & (b < 100)) > .35

    @staticmethod
    def terms_checked(frame: np.ndarray, label: Match) -> bool:
        x, y = label.center
        x -= 168
        roi = frame[max(0, y - 30):y + 26, max(0, x - 28):x + 30].astype(np.int16)
        b, g, r = roi[:, :, 0], roi[:, :, 1], roi[:, :, 2]
        return np.count_nonzero((g > 185) & (g > r * 1.35) & (g > b * 1.1)) > 35


class AdbDevice:
    def __init__(self, adb: str, serial: str, runner: Callable, writer: Callable,
                 package: str = PACKAGE):
        self.adb, self.serial = adb, serial
        self.runner, self.writer, self.package = runner, writer, package

    def run(self, *args: str, **kwargs) -> bytes:
        return self.runner(self.adb, "-s", self.serial, *args, **kwargs)

    def launch(self, reset: bool = False) -> None:
        if not re.fullmatch(r"[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)+", self.package):
            raise ValueError("Tên gói game không hợp lệ.")
        if reset:
            self.run("shell", "am", "force-stop", self.package)
        raw = self.run("shell", "monkey", "-p", self.package, "1")
        if b"No activities found" in raw:
            raise ValueError("OMG 3Q chưa được cài trong thiết bị này.")

    def capture(self) -> bytes:
        return self.run("exec-out", "screencap", "-p", timeout=20)

    def tap(self, x: int, y: int, frame_size: tuple[int, int]) -> None:
        width, height = frame_size
        self.run("shell", "input", "tap", str(round(x * width / SIZE[0])),
                 str(round(y * height / SIZE[1])))

    def replace_text(self, value: str) -> None:
        if not value or len(value) > 128 or any(ord(c) < 32 or ord(c) > 126 for c in value) or "%s" in value:
            raise ValueError("Tài khoản/mật khẩu phải dài 1–128 ký tự ASCII, không chứa chuỗi '%s'.")
        # Cocos/ZingID ignores Ctrl+A. Delete both sides of the caret before typing.
        self.run("shell", "input", "keyevent", "123", *(["67"] * 128), *(["112"] * 128))
        self.writer(self.adb, self.serial, value)


class LoginEngine:
    def __init__(self, device: AdbDevice, *, stop: threading.Event | None = None,
                 progress: Callable[[str], None] | None = None,
                 preview: Callable[[bytes], None] | None = None,
                 detector: Detector | None = None, timeout: float = 180,
                 clock: Callable = time.monotonic, sleeper: Callable | None = None,
                 startup_delay: float = 6):
        self.device = device
        self.stop = stop or threading.Event()
        self.progress = progress or (lambda message: None)
        self.preview = preview or (lambda png: None)
        self.detector = detector or Detector()
        self.timeout, self.clock = timeout, clock
        self.startup_delay = startup_delay
        self.sleeper = sleeper or self.stop.wait
        self.frame_size = SIZE
        self.last_png = b""

    def _wait(self, seconds: float = .8) -> None:
        self.sleeper(seconds)
        if self.stop.is_set():
            raise InterruptedError()

    def _observe(self) -> np.ndarray:
        if self.stop.is_set():
            raise InterruptedError()
        self.last_png = self.device.capture()
        raw = cv2.imdecode(np.frombuffer(self.last_png, np.uint8), cv2.IMREAD_COLOR)
        if raw is None:
            raise ValueError("Ảnh chụp không hợp lệ.")
        self.frame_size = raw.shape[1], raw.shape[0]
        frame = self.detector.decode(self.last_png)
        self.preview(self.last_png)
        return frame

    def _tap(self, match: Match, dx: int = 0, dy: int = 0) -> None:
        x, y = match.center
        self.device.tap(x + dx, y + dy, self.frame_size)

    def _form(self, frame: np.ndarray) -> Match | None:
        title = self.detector.find(frame, "zingid_form")
        return title if title and self.detector.find(frame, "cancel", .85) else None

    def _fill_and_submit(self, username: str, password: str) -> None:
        for offset, value, label in ((82, username, "tài khoản"), (166, password, "mật khẩu")):
            frame = self._observe()
            form = self._form(frame)
            if form is None:
                raise ValueError("Biểu mẫu đăng nhập đã thay đổi. Đã dừng nhập.")
            self.progress(f"Đang nhập {label}…")
            self._tap(form, dy=offset)
            self.device.replace_text(value)
            self._wait(1.1)  # Wait until Android has masked the final password character.
        frame = self._observe()
        submit = self.detector.find(frame, "submit", .94)
        if self._form(frame) is None or submit is None or not self.detector.orange_button(frame, submit):
            raise ValueError("Nút Đăng nhập chưa sẵn sàng; chưa gửi thông tin.")
        self.progress("Đang xác thực ZingID…")
        self._tap(submit)

    def _finish(self, status: str, message: str, save_image: bool = False) -> LoginResult:
        path = ""
        if save_image and self.last_png:
            try:
                frame = self.detector.decode(self.last_png)
                # Never persist the contents of either credential field in diagnostics.
                form = self.detector.find(frame, "zingid_form", .80)
                frame[385:565, 675:1245] = (28, 28, 28)
                if form:
                    x, y = form.center
                    frame[max(0, y + 30):min(SIZE[1], y + 220),
                          max(0, x - 300):min(SIZE[0], x + 300)] = (28, 28, 28)
                folder = ROOT / "runtime"
                folder.mkdir(exist_ok=True)
                output = folder / "login_last_screen.png"
                output.write_bytes(cv2.imencode(".png", frame)[1].tobytes())
                path = str(output)
            except Exception:
                # A failed diagnostic must not hide the original login error.
                path = ""
        self.progress(message)
        return LoginResult(status, message, path)

    def run(self, username: str, password: str, *, accept_terms: bool = False,
            enter_game: bool = True, prefer_played_server: bool = True,
            reset: bool = True) -> LoginResult:
        submitted = False
        submitted_at = 0.0
        switched = False
        switch_at = 0.0
        auth_requested = False
        post_auth_restart = False
        terms_tap_at = None
        server_chosen = not prefer_played_server
        empty_server_at = None
        entered_at = None
        lobby_frames = 0
        start = self.clock()
        ready_after = start + (self.startup_delay if reset else 0)
        try:
            if self.stop.is_set():
                raise InterruptedError()
            if not username or not password:
                raise ValueError("Chưa chọn tài khoản hoặc chưa có mật khẩu chung.")
            if len(username) > 128 or len(password) > 128:
                raise ValueError("Tài khoản/mật khẩu vượt giới hạn 128 ký tự.")
            self.progress("Đang mở OMG 3Q…")
            if reset:
                self.device.launch(reset=True)
            while self.clock() - start < self.timeout:
                frame = self._observe()
                find = lambda name, threshold=.92: self.detector.find(frame, name, threshold)
                if entered_at is not None:
                    confirmation = find("announcement_confirm", .94)
                    if find("lobby_announcement", .94) and confirmation:
                        self.progress("Đóng thông báo khi vào game…")
                        self._tap(confirmation)
                        self._wait()
                        continue
                    dismiss = find("promo_dismiss", .90)
                    if dismiss:
                        self.progress("Đóng bảng giới thiệu sự kiện…")
                        self._tap(dismiss)
                        self._wait()
                        continue
                notice = find("notice_accept", .94)
                if notice:
                    self.progress("Đóng thông báo khởi động…")
                    self._tap(notice)
                    if not submitted:
                        switched, auth_requested = False, False
                        terms_tap_at = None
                    self._wait()
                    continue
                provider = find("zingid", .95)
                if provider:
                    if submitted:
                        return self._finish("failed", "Phiên đăng nhập bị trả về màn hình ZingID.", True)
                    self.progress("Chọn đăng nhập bằng ZingID…")
                    self._tap(provider)
                    self._wait()
                    continue
                form = self._form(frame)
                if form:
                    if not submitted:
                        self._fill_and_submit(username, password)
                        submitted, submitted_at = True, self.clock()
                    elif self.clock() - submitted_at > 15:
                        return self._finish("failed", "Game chưa xác thực được tài khoản. Kiểm tra thông báo trong giả lập.", True)
                    self._wait()
                    continue
                # Opening ZingID with "Vào Game" can auto-enter the last selected
                # server after authentication. Reopen the title once so server history
                # belongs to the newly authenticated account before selecting a role.
                if submitted and auth_requested and not post_auth_restart:
                    authenticated_screen = (find("start_game", .94) or find("lobby_status")
                                            or find("lobby_announcement") or find("promo_dismiss", .90))
                    if authenticated_screen:
                        if self.clock() - submitted_at < 2:
                            self._wait()
                            continue
                        self.progress("Xác thực xong; mở lại màn hình chọn server của tài khoản…")
                        self.device.launch(reset=True)
                        post_auth_restart = True
                        terms_tap_at = None
                        ready_after = self.clock() + self.startup_delay
                        self._wait(2)
                        continue
                if find("server_panel", .94):
                    if not submitted:
                        return self._finish("unknown", "Chưa xác thực tài khoản được chọn; đã dừng.", True)
                    tab = find("played_tab", .90)
                    if tab is None:
                        return self._finish("unknown", "Chưa nhận diện được tab server đã chơi.", True)
                    card = self.detector.first_played_card(frame)
                    if card:
                        self.progress("Chọn server đầu tiên có nhân vật trong Tập hợp Server…")
                        self._tap(card, dx=232, dy=40)
                        server_chosen = True
                        terms_tap_at = None
                        self._wait(1)
                        continue
                    if empty_server_at is None:
                        empty_server_at = self.clock()
                    if self.clock() - empty_server_at > 5:
                        return self._finish("needs_character", "Tài khoản chưa có server đã chơi. Đã dừng trước bước tạo nhân vật.", True)
                    self._wait()
                    continue
                start_button = find("start_game", .94)
                switch = find("switch_account", .94)
                if start_button and switch:
                    if self.clock() < ready_after:
                        self._wait()
                        continue
                    if not submitted:
                        if not switched:
                            self.progress("Mở Đổi Tài Khoản để dùng tài khoản được chọn…")
                            self._tap(switch)
                            switched, switch_at = True, self.clock()
                        elif self.clock() - switch_at > 18:
                            return self._finish("unknown", "Không mở được biểu mẫu Đổi Tài Khoản.", True)
                        elif not auth_requested and self.clock() - switch_at > 1:
                            terms = find("terms_label", .90)
                            if terms is None:
                                return self._finish("unknown", "Không nhận diện được điều khoản trước bước mở ZingID.", True)
                            if not self.detector.terms_checked(frame, terms):
                                if not accept_terms:
                                    return self._finish("needs_terms", "Cần cho phép tích ô điều khoản để mở biểu mẫu ZingID.")
                                if terms_tap_at is None:
                                    self._tap(terms, dx=-168)
                                    terms_tap_at = self.clock()
                                elif self.clock() - terms_tap_at > 3:
                                    return self._finish("unknown", "Ô điều khoản chưa được bật; đã dừng để tránh bấm nhầm.", True)
                            else:
                                self.progress("Mở biểu mẫu xác thực tài khoản…")
                                self._tap(start_button)
                                auth_requested = True
                        self._wait()
                        continue
                    if not enter_game:
                        return self._finish("authenticated", "Đã xác thực tài khoản, đang ở màn hình chọn server.")
                    if not server_chosen:
                        chooser = find("choose_server", .94)
                        if chooser:
                            self.progress("Tìm server đã chơi…")
                            self._tap(chooser)
                        self._wait()
                        continue
                    terms = find("terms_label", .90)
                    if terms is None:
                        return self._finish("unknown", "Chưa xác nhận được trạng thái ô điều khoản.", True)
                    if not self.detector.terms_checked(frame, terms):
                        if not accept_terms:
                            return self._finish("needs_terms", "Cần tích ô đồng ý điều khoản trong game trước khi vào.")
                        if terms_tap_at is None:
                            self.progress("Tích ô điều khoản theo quyền đã cho phép…")
                            self._tap(terms, dx=-168)
                            terms_tap_at = self.clock()
                        elif self.clock() - terms_tap_at > 3:
                            return self._finish("unknown", "Ô điều khoản chưa được bật; đã dừng để tránh bấm nhầm.", True)
                        self._wait()
                        continue
                    if entered_at is None:
                        self.progress("Vào game trên server có nhân vật…")
                        self._tap(start_button)
                        entered_at = self.clock()
                    elif self.clock() - entered_at > 25:
                        return self._finish("failed", "Game chưa vào được server đã chọn. Kiểm tra kết nối hoặc thông báo máy chủ.", True)
                    self._wait()
                    continue
                if find("create_character", .94):
                    return self._finish("needs_character", "Game yêu cầu tạo nhân vật. Đã dừng.", True)
                status, menu = find("lobby_status", .92), find("lobby_menu", .92)
                if (entered_at is not None and status and menu
                        and self.detector.unobscured(frame, status)
                        and self.detector.unobscured(frame, menu)):
                    lobby_frames += 1
                    if lobby_frames >= 2:
                        return self._finish("success", "Đăng nhập thành công và đã vào game trên server đã chơi.")
                else:
                    lobby_frames = 0
                self._wait()
            return self._finish("timeout", "Hết thời gian chờ: game đang ở màn hình chưa nhận diện được. Đã dừng.", True)
        except InterruptedError:
            return self._finish("cancelled", "Đã dừng đăng nhập.")
        except Exception as exc:
            message = str(exc).replace(password, "[đã ẩn]") if password else str(exc)
            return self._finish("error", f"Đã dừng: {message}", True)
