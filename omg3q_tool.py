"""MuMu Player 12 automation for OMG 3Q. Run with the project's virtual environment."""

from __future__ import annotations

import base64
import json
import os
import queue
import re
import shlex
import shutil
import subprocess
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

from login_engine import (AdbDevice, LoginEngine, PACKAGE, load_accounts,
                          load_common_password, load_options, save_options)


TITLE = "OMG 3Q · Công cụ thao tác MuMu"
CONFIG_FILE = Path(__file__).with_name("omg3q_steps.json")
DEFAULT_ADB = Path(r"C:\Program Files\Netease\MuMuPlayerGlobal-12.0\nx_main\adb.exe")
DEFAULT_MANAGER = Path(r"C:\Program Files\Netease\MuMuPlayerGlobal-12.0\nx_main\MuMuManager.exe")
MAX_IMAGE_WIDTH = 900
MAX_IMAGE_HEIGHT = 510


class AdbError(RuntimeError):
    pass


def find_adb() -> str:
    if DEFAULT_ADB.is_file():
        return str(DEFAULT_ADB)
    found = shutil.which("adb")
    if found:
        return found
    raise AdbError("Không tìm thấy adb.exe của MuMu. Hãy kiểm tra đường dẫn cài MuMu Player 12.")


def run_adb(adb: str, *args: str, timeout: int = 25, data: bytes | None = None) -> bytes:
    try:
        server_port = os.environ.get("OMG_ADB_SERVER_PORT")
        prefix = [adb, "-P", server_port] if server_port and server_port.isdigit() else [adb]
        result = subprocess.run(
            [*prefix, *args],
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AdbError(f"ADB không phản hồi: {exc}") from exc
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise AdbError(detail or f"ADB trả về mã lỗi {result.returncode}.")
    return result.stdout


def connect(adb: str, serial: str) -> tuple[int, int]:
    if not re.fullmatch(r"(?:127\.0\.0\.1|localhost):\d{2,5}", serial):
        raise AdbError("Địa chỉ ADB phải có dạng 127.0.0.1:16384.")
    reply = run_adb(adb, "connect", serial, timeout=15).decode("utf-8", "replace")
    if "connected" not in reply and "already" not in reply:
        raise AdbError(f"Không kết nối được MuMu: {reply.strip()}")
    state = run_adb(adb, "-s", serial, "get-state").decode("utf-8", "replace").strip()
    if state != "device":
        raise AdbError(f"Thiết bị chưa sẵn sàng: {state}")
    size = run_adb(adb, "-s", serial, "shell", "wm", "size").decode("utf-8", "replace")
    match = re.search(r"(\d+)x(\d+)", size)
    if not match:
        raise AdbError(f"Không đọc được độ phân giải thiết bị: {size.strip()}")
    return int(match.group(1)), int(match.group(2))


def screenshot(adb: str, serial: str) -> bytes:
    result = run_adb(adb, "-s", serial, "exec-out", "screencap", "-p", timeout=30)
    if not result.startswith(b"\x89PNG\r\n\x1a\n"):
        raise AdbError("MuMu không trả về ảnh chụp màn hình PNG.")
    return result


def tap(adb: str, serial: str, x: int, y: int) -> None:
    run_adb(adb, "-s", serial, "shell", "input", "tap", str(x), str(y))


def input_text(adb: str, serial: str, value: str) -> None:
    """Send text via stdin so credentials never appear in Windows process arguments."""
    if not value or any(ord(ch) < 32 or ord(ch) > 126 for ch in value):
        raise AdbError("ADB chỉ nhập ổn định ký tự ASCII 32–126; kiểm tra tài khoản/mật khẩu.")
    if "%s" in value:
        raise AdbError("Chuỗi '%s' chưa được hỗ trợ bởi lệnh nhập văn bản của Android.")
    encoded = value.replace(" ", "%s")
    command = f"input text {shlex.quote(encoded)}\nexit\n".encode("ascii")
    try:
        run_adb(adb, "-s", serial, "shell", timeout=25, data=command)
    except AdbError:
        raise AdbError("Không nhập được nội dung vào game. Đã dừng để bảo vệ thông tin đăng nhập.") from None


def launch_game(adb: str, serial: str, package: str) -> None:
    if not re.fullmatch(r"[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)+", package):
        raise AdbError("Tên gói game chưa hợp lệ. Dùng nút 'Tìm ứng dụng' để chọn.")
    reply = run_adb(adb, "-s", serial, "shell", "monkey", "-p", package, "1")
    if b"No activities found" in reply or b"Events injected: 0" in reply:
        raise AdbError(f"Không mở được ứng dụng {package}.")


def installed_packages(adb: str, serial: str) -> list[str]:
    raw = run_adb(adb, "-s", serial, "shell", "pm", "list", "packages", "-3", timeout=40)
    return sorted(line[8:].strip() for line in raw.decode("utf-8", "replace").splitlines()
                  if line.startswith("package:"))


def foreground_package(adb: str, serial: str) -> str:
    raw = run_adb(adb, "-s", serial, "shell", "dumpsys", "window", timeout=30)
    text = raw.decode("utf-8", "replace")
    for pattern in (r"mCurrentFocus[^\n]*?\bu\d+\s+([\w.]+)/",
                    r"mCurrentFocus[^\n]*?\s([\w.]+)/"):
        match = re.search(pattern, text)
        if match:
            package = match.group(1)
            if package not in {"com.android.systemui", "com.android.launcher3"}:
                return package
    raise AdbError("Chưa nhận ra game đang mở. Hãy vào OMG 3Q rồi thử lại, hoặc dùng 'Tìm ứng dụng'.")


def load_config() -> dict:
    if not CONFIG_FILE.is_file():
        return {"serial": "127.0.0.1:16384", "package": PACKAGE, "steps": []}
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("steps"), list):
            raise ValueError("Tệp cấu hình sai định dạng")
        return data
    except (OSError, ValueError) as exc:
        raise AdbError(f"Không đọc được {CONFIG_FILE.name}: {exc}") from exc


def save_config(serial: str, package: str, steps: list[dict]) -> None:
    # Only layout coordinates and timing are persisted; never account credentials.
    data = {"serial": serial, "package": package, "steps": steps}
    temporary = CONFIG_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(CONFIG_FILE)


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title(TITLE)
        root.geometry("1230x850")
        root.minsize(1020, 700)
        self.events: queue.Queue = queue.Queue()
        self.busy = False
        self.stop_event = threading.Event()
        self.adb = find_adb()
        config = load_config()
        self.serial = tk.StringVar(value=config.get("serial", "127.0.0.1:16384"))
        self.package = tk.StringVar(value=config.get("package") or PACKAGE)
        self.username = tk.StringVar()
        self.password = tk.StringVar(value=load_common_password())
        options = load_options()
        self.accept_terms = tk.BooleanVar(value=options["accept_terms"])
        self.enter_game = tk.BooleanVar(value=options["enter_game"])
        self.prefer_played = tk.BooleanVar(value=options["prefer_played_server"])
        self.accounts = []
        self.account_count = tk.StringVar()
        self.status = tk.StringVar(value="Chọn tài khoản trong account.txt rồi bấm Đăng nhập.")
        self.step_name = tk.StringVar(value="Chạm")
        self.steps: list[dict] = config.get("steps", [])
        self.capture_size = (0, 0)
        self.image_scale = 1
        self.image = None
        self.add_tap_pending = False
        self._build()
        self.reload_accounts(show_error=False)
        self._refresh_steps()
        root.protocol("WM_DELETE_WINDOW", self._close)
        root.after(100, self._drain_events)

    def _build(self) -> None:
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="ADB MuMu").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.serial, width=23).grid(row=0, column=1, padx=5)
        ttk.Button(top, text="Kết nối", command=self.connect_async).grid(row=0, column=2, padx=5)
        ttk.Button(top, text="Mở MuMu", command=self.start_mumu).grid(row=0, column=3, padx=5)
        ttk.Label(top, text="Gói game").grid(row=0, column=4, padx=(20, 0))
        ttk.Entry(top, textvariable=self.package, width=24).grid(row=0, column=5, padx=5)
        ttk.Button(top, text="Tìm ứng dụng", command=self.find_packages).grid(row=0, column=6)
        ttk.Button(top, text="Dùng game đang mở", command=self.use_foreground).grid(row=0, column=7, padx=5)

        credential = ttk.LabelFrame(self.root, text="Đăng nhập ZingID · danh sách từ account.txt", padding=9)
        credential.pack(fill="x", padx=10)
        ttk.Label(credential, text="Tên đăng nhập").grid(row=0, column=0)
        self.account_combo = ttk.Combobox(credential, textvariable=self.username, width=27, state="readonly")
        self.account_combo.grid(row=0, column=1, padx=8)
        ttk.Button(credential, text="Nạp lại danh sách", command=self.reload_accounts).grid(row=0, column=2)
        ttk.Label(credential, text="Mật khẩu chung").grid(row=0, column=3, padx=(18, 0))
        ttk.Entry(credential, textvariable=self.password, show="●", width=24).grid(row=0, column=4, padx=8)
        ttk.Label(credential, textvariable=self.account_count).grid(row=0, column=5, padx=8)
        ttk.Checkbutton(credential, text="Ưu tiên server đã chơi", variable=self.prefer_played).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Checkbutton(credential, text="Vào game sau xác thực", variable=self.enter_game).grid(row=1, column=2, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Checkbutton(credential, text="Cho phép tích ô đồng ý điều khoản game", variable=self.accept_terms).grid(row=1, column=4, columnspan=2, sticky="w", pady=(8, 0))

        body = ttk.Frame(self.root, padding=10)
        body.pack(fill="both", expand=True)
        left = ttk.LabelFrame(body, text="Ảnh giả lập · bấm lên ảnh để thêm bước chạm", padding=6)
        left.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(left, width=MAX_IMAGE_WIDTH, height=MAX_IMAGE_HEIGHT,
                                bg="#202533", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_text(380, 250, text="Bấm “Chụp màn hình”", fill="white", tags="placeholder")
        self.canvas.bind("<Button-1>", self._canvas_click)
        ttk.Button(left, text="Chụp màn hình", command=self.capture_async).pack(fill="x", pady=(8, 0))

        right = ttk.LabelFrame(body, text="Kịch bản nâng cao (tùy chọn)", padding=7)
        right.pack(side="right", fill="y", padx=(10, 0))
        right.configure(width=275)
        ttk.Label(right, text="Tên bước chạm").pack(anchor="w")
        ttk.Entry(right, textvariable=self.step_name, width=30).pack(fill="x", pady=(2, 6))
        ttk.Button(right, text="Thêm chạm trên ảnh", command=self._prepare_tap).pack(fill="x")
        ttk.Button(right, text="Thêm mở game", command=lambda: self._add_step({"action": "launch"})).pack(fill="x", pady=(6, 0))
        ttk.Button(right, text="Thêm nhập tài khoản", command=lambda: self._add_step({"action": "username"})).pack(fill="x", pady=(6, 0))
        ttk.Button(right, text="Thêm nhập mật khẩu", command=lambda: self._add_step({"action": "password"})).pack(fill="x", pady=(6, 0))
        ttk.Button(right, text="Thêm thời gian đợi", command=self._add_wait).pack(fill="x", pady=(6, 0))
        self.listbox = tk.Listbox(right, width=33, height=16, exportselection=False)
        self.listbox.pack(fill="both", expand=True, pady=10)
        row = ttk.Frame(right)
        row.pack(fill="x")
        ttk.Button(row, text="Lên", command=lambda: self._move(-1)).pack(side="left", expand=True, fill="x")
        ttk.Button(row, text="Xuống", command=lambda: self._move(1)).pack(side="left", expand=True, fill="x")
        ttk.Button(row, text="Xóa", command=self._delete).pack(side="left", expand=True, fill="x")
        ttk.Button(right, text="Lưu các bước", command=self._save).pack(fill="x", pady=(9, 0))
        ttk.Button(right, text="Chạy kịch bản nâng cao", command=self.run_steps).pack(fill="x", pady=(6, 0))

        foot = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        foot.pack(fill="x")
        ttk.Button(foot, text="Đăng nhập tài khoản đã chọn", command=self.run_login).pack(side="left")
        ttk.Button(foot, text="Dừng sau bước hiện tại", command=self.stop_event.set).pack(side="left", padx=8)
        ttk.Label(foot, textvariable=self.status, wraplength=850).pack(side="left", padx=12)

    def _close(self) -> None:
        self.stop_event.set()
        self.root.destroy()

    def reload_accounts(self, show_error: bool = True) -> bool:
        if self.busy:
            self.status.set("Đang chạy; danh sách tài khoản sẽ nạp lại sau khi dừng.")
            return False
        try:
            accounts = load_accounts()
        except ValueError as exc:
            self.accounts = []
            self.account_combo.configure(values=[])
            self.username.set("")
            self.account_count.set("Chưa có tài khoản")
            if show_error:
                messagebox.showerror("Danh sách tài khoản", str(exc))
            return False
        current = self.username.get()
        self.accounts = accounts
        self.account_combo.configure(values=accounts)
        self.username.set(current if current in accounts else accounts[0])
        self.account_count.set(f"{len(accounts)} tài khoản")
        return True

    def run_login(self) -> None:
        if self.busy:
            self.status.set("Đang thực hiện một thao tác khác.")
            return
        if not self.reload_accounts():
            return
        username, password = self.username.get(), self.password.get()
        if not username or username not in self.accounts or not password:
            messagebox.showinfo("Đăng nhập", "Chọn tài khoản trong account.txt và nhập mật khẩu chung.")
            return
        options = {"accept_terms": self.accept_terms.get(), "enter_game": self.enter_game.get(),
                   "prefer_played_server": self.prefer_played.get()}
        serial, package = self.serial.get().strip(), self.package.get().strip() or PACKAGE
        try:
            save_options(options)
            save_config(serial, package, self.steps)
        except OSError as exc:
            messagebox.showerror("Cấu hình đăng nhập", str(exc))
            return
        self.stop_event.clear()

        def work():
            connect(self.adb, serial)
            device = AdbDevice(self.adb, serial, run_adb, input_text, package)
            engine = LoginEngine(device, stop=self.stop_event,
                                 progress=lambda text: self.events.put(("progress", text, None)),
                                 preview=lambda png: self.events.put(("frame", png, None)))
            return engine.run(username, password, **options)

        self._worker(work, self._login_complete)

    def _login_complete(self, result) -> None:
        self.last_result = result
        self.status.set(result.message)
        if result.status in {"error", "failed", "timeout", "unknown"}:
            messagebox.showwarning("Đăng nhập đã dừng", result.message +
                                   (f"\nẢnh chẩn đoán: {result.screenshot}" if result.screenshot else ""))

    def _set_busy(self, value: bool, message: str | None = None) -> None:
        self.busy = value
        self.account_combo.configure(state="disabled" if value else "readonly")
        if message:
            self.status.set(message)

    def _worker(self, func, done=None) -> None:
        if self.busy:
            self.status.set("Đang thực hiện một thao tác khác.")
            return
        self._set_busy(True)

        def runner():
            try:
                result = func()
                self.events.put(("ok", result, done))
            except Exception as exc:  # Show errors on Tk's main thread.
                self.events.put(("error", str(exc), None))

        threading.Thread(target=runner, daemon=True).start()

    def _drain_events(self) -> None:
        try:
            while True:
                kind, value, done = self.events.get_nowait()
                if kind == "progress":
                    self.status.set(value)
                elif kind == "frame":
                    self._show_image(value, update_status=False)
                elif kind == "error":
                    self._set_busy(False, value)
                    messagebox.showerror("OMG 3Q", value)
                else:
                    self._set_busy(False)
                    if done:
                        done(value)
        except queue.Empty:
            pass
        self.root.after(100, self._drain_events)

    def connect_async(self) -> None:
        serial = self.serial.get().strip()
        self._worker(lambda: connect(self.adb, serial),
                     lambda size: self.status.set(f"Đã kết nối MuMu · {size[0]}×{size[1]}"))

    def start_mumu(self) -> None:
        if not DEFAULT_MANAGER.is_file():
            messagebox.showerror("MuMu", "Không tìm thấy MuMuManager.exe.")
            return
        try:
            subprocess.Popen([str(DEFAULT_MANAGER), "control", "--vmindex", "0", "launch"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.status.set("Đang mở MuMu. Đợi thiết bị khởi động rồi bấm Kết nối.")
        except OSError as exc:
            messagebox.showerror("MuMu", str(exc))

    def capture_async(self) -> None:
        serial = self.serial.get().strip()
        self._worker(lambda: screenshot(self.adb, serial), self._show_image)

    def _show_image(self, png: bytes, update_status: bool = True) -> None:
        try:
            image = tk.PhotoImage(data=base64.b64encode(png).decode("ascii"), format="png")
            original = (image.width(), image.height())
            scale = max(1, (original[0] + MAX_IMAGE_WIDTH - 1) // MAX_IMAGE_WIDTH,
                        (original[1] + MAX_IMAGE_HEIGHT - 1) // MAX_IMAGE_HEIGHT)
            if scale > 1:
                image = image.subsample(scale, scale)
            self.image = image
            self.image_scale = scale
            self.capture_size = original
            self.canvas.delete("all")
            self.canvas.config(width=image.width(), height=image.height())
            self.canvas.create_image(0, 0, image=image, anchor="nw")
            if update_status:
                self.status.set(f"Ảnh {original[0]}×{original[1]}. Chọn “Thêm chạm trên ảnh” rồi bấm vị trí cần thao tác.")
        except tk.TclError as exc:
            messagebox.showerror("Ảnh màn hình", str(exc))

    def find_packages(self) -> None:
        serial = self.serial.get().strip()
        self._worker(lambda: installed_packages(self.adb, serial), self._show_packages)

    def use_foreground(self) -> None:
        serial = self.serial.get().strip()
        self._worker(lambda: foreground_package(self.adb, serial), self._set_foreground)

    def _set_foreground(self, package: str) -> None:
        self.package.set(package)
        self.status.set(f"Đã chọn game đang mở: {package}")

    def _show_packages(self, packages: list[str]) -> None:
        if not packages:
            messagebox.showinfo("Ứng dụng", "Chưa tìm thấy ứng dụng bên thứ ba trên thiết bị.")
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("Chọn gói game")
        dialog.geometry("520x410")
        ttk.Label(dialog, text="Chọn gói OMG 3Q trong danh sách:", padding=9).pack(anchor="w")
        box = tk.Listbox(dialog, width=70)
        box.pack(fill="both", expand=True, padx=9)
        for package in packages:
            box.insert("end", package)
        matches = [i for i, package in enumerate(packages) if re.search(r"omg|3q|vng|game", package, re.I)]
        if matches:
            box.selection_set(matches[0])
            box.see(matches[0])

        def select():
            picked = box.curselection()
            if picked:
                self.package.set(packages[picked[0]])
                dialog.destroy()

        ttk.Button(dialog, text="Chọn", command=select).pack(pady=9)
        dialog.transient(self.root)
        dialog.grab_set()

    def _prepare_tap(self) -> None:
        if self.image is None:
            messagebox.showinfo("Chưa có ảnh", "Hãy chụp màn hình trước.")
            return
        self.add_tap_pending = True
        self.status.set("Bấm vào vị trí trên ảnh cần tool chạm.")

    def _canvas_click(self, event) -> None:
        if not self.add_tap_pending or not self.capture_size:
            return
        x = min(self.capture_size[0] - 1, event.x * self.image_scale)
        y = min(self.capture_size[1] - 1, event.y * self.image_scale)
        if x < 0 or y < 0:
            return
        self.add_tap_pending = False
        self._add_step({"action": "tap", "x": x, "y": y,
                        "width": self.capture_size[0], "height": self.capture_size[1],
                        "label": self.step_name.get().strip() or "Chạm"})
        self.canvas.create_oval(event.x - 5, event.y - 5, event.x + 5, event.y + 5,
                                outline="#ffeb3b", width=2)
        self.status.set(f"Đã thêm bước chạm {x}, {y}.")

    def _add_wait(self) -> None:
        seconds = simpledialog.askfloat("Thời gian đợi", "Số giây cần đợi:",
                                        parent=self.root, initialvalue=3, minvalue=0.1, maxvalue=120)
        if seconds is not None:
            self._add_step({"action": "wait", "seconds": seconds})

    def _add_step(self, step: dict) -> None:
        self.steps.append(step)
        self._refresh_steps()
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set("end")

    def _describe(self, step: dict) -> str:
        action = step.get("action")
        if action == "tap":
            return f"{step.get('label', 'Chạm')} ({step['x']}, {step['y']})"
        if action == "launch":
            return "Mở game"
        if action == "username":
            return "Nhập tài khoản"
        if action == "password":
            return "Nhập mật khẩu"
        if action == "wait":
            return f"Đợi {step['seconds']:g} giây"
        return f"Bước không rõ: {action}"

    def _refresh_steps(self) -> None:
        self.listbox.delete(0, "end")
        for i, step in enumerate(self.steps, 1):
            self.listbox.insert("end", f"{i}. {self._describe(step)}")

    def _selected(self) -> int | None:
        selection = self.listbox.curselection()
        return selection[0] if selection else None

    def _move(self, direction: int) -> None:
        index = self._selected()
        if index is None or not 0 <= index + direction < len(self.steps):
            return
        other = index + direction
        self.steps[index], self.steps[other] = self.steps[other], self.steps[index]
        self._refresh_steps()
        self.listbox.selection_set(other)

    def _delete(self) -> None:
        index = self._selected()
        if index is not None:
            self.steps.pop(index)
            self._refresh_steps()

    def _save(self) -> None:
        try:
            save_config(self.serial.get().strip(), self.package.get().strip(), self.steps)
            self.status.set(f"Đã lưu {len(self.steps)} bước. Tài khoản và mật khẩu không được lưu.")
        except OSError as exc:
            messagebox.showerror("Lưu", str(exc))

    def clear_credentials(self) -> None:
        self.username.set("")
        self.password.set("")
        self.status.set("Đã xóa tài khoản và mật khẩu khỏi cửa sổ tool.")

    def run_steps(self) -> None:
        if not self.steps:
            messagebox.showinfo("Chưa có bước", "Hãy tạo các bước đăng nhập trước.")
            return
        serial = self.serial.get().strip()
        package = self.package.get().strip()
        username = self.username.get()
        password = self.password.get()
        steps = [step.copy() for step in self.steps]
        if any(step.get("action") == "username" for step in steps) and not username:
            messagebox.showinfo("Tài khoản", "Hãy nhập tên tài khoản.")
            return
        if any(step.get("action") == "password" for step in steps) and not password:
            messagebox.showinfo("Mật khẩu", "Hãy nhập mật khẩu.")
            return
        self.stop_event.clear()

        def work():
            width, height = connect(self.adb, serial)
            for i, step in enumerate(steps, 1):
                if self.stop_event.is_set():
                    return "Đã dừng."
                action = step.get("action")
                self.events.put(("progress", f"Bước {i}/{len(steps)}: {self._describe(step)}", None))
                if action == "launch":
                    if not package:
                        raise AdbError("Chưa chọn gói game. Dùng nút 'Tìm ứng dụng'.")
                    launch_game(self.adb, serial, package)
                elif action == "tap":
                    sw, sh = int(step["width"]), int(step["height"])
                    if sw <= 0 or sh <= 0:
                        raise AdbError("Kích thước ảnh trong bước chạm không hợp lệ.")
                    x = min(width - 1, round(int(step["x"]) * width / sw))
                    y = min(height - 1, round(int(step["y"]) * height / sh))
                    tap(self.adb, serial, x, y)
                elif action == "username":
                    input_text(self.adb, serial, username)
                elif action == "password":
                    input_text(self.adb, serial, password)
                elif action == "wait":
                    end = time.monotonic() + float(step["seconds"])
                    while time.monotonic() < end:
                        if self.stop_event.wait(min(0.2, end - time.monotonic())):
                            return "Đã dừng."
                else:
                    raise AdbError(f"Bước không được hỗ trợ: {action}")
            return "Đã chạy hết các bước. Chụp màn hình để kiểm tra kết quả đăng nhập."

        self._worker(work, lambda result: self.status.set(result))


def main() -> None:
    root = tk.Tk()
    try:
        App(root)
    except (AdbError, ValueError) as exc:
        messagebox.showerror("OMG 3Q", str(exc))
        root.destroy()
        return
    root.mainloop()


if __name__ == "__main__":
    main()
