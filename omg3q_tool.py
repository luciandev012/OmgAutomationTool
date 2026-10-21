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
from tkinter import filedialog, messagebox, simpledialog, ttk

from login_engine import AdbDevice, LoginEngine, PACKAGE
from account_excel import AccountWorkbook
from excel_scripts import ExcelCycle, ScriptBatch, shutdown_session
from dungeon_engine import DungeonDetector, DungeonEngine
from equipment_skill import EquipmentDetector, TeamEquipmentSkill
from emulator_instances import detect_emulators
from instance_dialog import InstanceDialog
from task_sessions import SessionRegistry, active_session, guard_command
from screen_observer import capture_screen


TITLE = "OMG 3Q · Công cụ tự động hóa"
CONFIG_FILE = Path(__file__).with_name("omg3q_steps.json")
DEFAULT_ADB = Path(r"C:\Program Files\Netease\MuMuPlayer\nx_main\adb.exe")
DEFAULT_MANAGER = Path(r"C:\Program Files\Netease\MuMuPlayer\nx_main\MuMuManager.exe")
MAX_IMAGE_WIDTH = 900
MAX_IMAGE_HEIGHT = 510


class AdbError(RuntimeError):
    pass


def find_ldmultiplayer() -> Path | None:
    """Find the instance manager, not dnplayer.exe or the console launcher."""
    hint = os.environ.get("OMG_LDMULTIPLAYER", "").strip().strip('"')
    if hint and Path(hint).is_file():
        return Path(hint)
    roots = [Path(r"C:\LDPlayer"), Path(r"C:\leidian")]
    for key, default in (("ProgramFiles", r"C:\Program Files"),
                         ("ProgramFiles(x86)", r"C:\Program Files (x86)")):
        roots.append(Path(os.environ.get(key, default)) / "LDPlayer")
    try:
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for key in (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"):
                try:
                    with winreg.OpenKey(hive, key) as parent:
                        for index in range(winreg.QueryInfoKey(parent)[0]):
                            try:
                                with winreg.OpenKey(parent, winreg.EnumKey(parent, index)) as child:
                                    label = str(winreg.QueryValueEx(child, "DisplayName")[0])
                                    if "ldplayer" not in label.lower():
                                        continue
                                    for value in ("InstallLocation", "DisplayIcon"):
                                        try:
                                            raw = str(winreg.QueryValueEx(child, value)[0]).strip()
                                            if not raw:
                                                continue
                                            path = Path(raw.rsplit(",", 1)[0].strip('"'))
                                            root = path.parent if value == "DisplayIcon" else path
                                            roots.extend((root, root.parent))
                                        except OSError:
                                            pass
                            except OSError:
                                continue
                except OSError:
                    continue
    except ImportError:
        pass
    relative_paths = ("ldmutiplayer/dnmultiplayerex.exe", "dnmultiplayerex.exe", "dnmultiplayer.exe")
    for root in dict.fromkeys(roots):
        for base in (root, *(root / folder for folder in ("LDPlayer14", "LDPlayer9", "LDPlayer64", "LDPlayer4"))):
            for relative in relative_paths:
                candidate = base / relative
                if candidate.is_file():
                    return candidate
    found = shutil.which("dnmultiplayerex.exe") or shutil.which("dnmultiplayer.exe")
    return Path(found) if found else None


def find_adb() -> str:
    if DEFAULT_ADB.is_file():
        return str(DEFAULT_ADB)
    found = shutil.which("adb")
    if found:
        return found
    raise AdbError("Không tìm thấy adb.exe của MuMu. Hãy kiểm tra đường dẫn cài MuMu Player 12.")


_adb_start_lock = threading.Lock()


def run_adb(adb: str, *args: str, timeout: int = 25, data: bytes | None = None) -> bytes:
    guard_command(adb, args)
    try:
        server_port = os.environ.get("OMG_ADB_SERVER_PORT")
        prefix = [adb, "-H", "127.0.0.1"]
        if server_port and server_port.isdigit():
            prefix += ["-P", server_port]
        result = subprocess.run(
            [*prefix, *args],
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode and b"cannot connect to daemon at tcp:127.0.0.1:" in result.stderr:
            # -H disables automatic daemon startup, even for loopback. Start
            # locally without -H, then keep explicit IPv4 for device commands.
            with _adb_start_lock:
                guard_command(adb, args)
                probe = subprocess.run(
                    [*prefix, "start-server"], capture_output=True, timeout=timeout,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if probe.returncode:
                    port = server_port if server_port and server_port.isdigit() else "5037"
                    started = subprocess.run(
                        [adb, "-L", f"tcp:{port}", "start-server"],
                        capture_output=True, timeout=timeout,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    if started.returncode:
                        detail = started.stderr.decode("utf-8", "replace").strip()
                        raise AdbError(f"Không khởi động được máy chủ ADB (cổng {port}): {detail}")
            guard_command(adb, args)
            result = subprocess.run(
                [*prefix, *args], input=data, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, timeout=timeout, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AdbError(f"ADB không phản hồi: {exc}") from exc
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise AdbError(detail or f"ADB trả về mã lỗi {result.returncode}.")
    return result.stdout


def connect(adb: str, serial: str) -> tuple[int, int]:
    if not re.fullmatch(r"(?:(?:127\.0\.0\.1|localhost):\d{2,5}|emulator-\d+)", serial):
        raise AdbError("Địa chỉ ADB phải có dạng 127.0.0.1:16384.")
    if ":" in serial:
        reply = run_adb(adb, "connect", serial, timeout=15).decode("utf-8", "replace")
        if "connected" not in reply and "already" not in reply:
            raise AdbError(f"Không kết nối được giả lập: {reply.strip()}")
    state = run_adb(adb, "-s", serial, "get-state").decode("utf-8", "replace").strip()
    if state != "device":
        raise AdbError(f"Thiết bị chưa sẵn sàng: {state}")
    size = run_adb(adb, "-s", serial, "shell", "wm", "size").decode("utf-8", "replace")
    match = re.search(r"(\d+)x(\d+)", size)
    if not match:
        raise AdbError(f"Không đọc được độ phân giải thiết bị: {size.strip()}")
    return int(match.group(1)), int(match.group(2))


def screenshot(adb: str, serial: str) -> bytes:
    result = capture_screen(adb, serial, run_adb)
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
        self.sessions = SessionRegistry()
        self.busy = False
        self.stop_event = threading.Event()
        # The instance manager can be opened even when MuMu ADB is absent.
        try:
            self.adb = find_adb()
        except AdbError:
            self.adb = ""
        self.providers = detect_emulators(DEFAULT_MANAGER, find_ldmultiplayer())
        self.provider_name = tk.StringVar(value=self.providers[0].label if self.providers else "")
        self.instance_dialog = None
        self.launch_control = None
        if self.providers:
            self.adb = str(self.providers[0].adb)
        config = load_config()
        self.serial = tk.StringVar(value=config.get("serial", "127.0.0.1:16384"))
        self.package = tk.StringVar(value=config.get("package") or PACKAGE)
        self.excel_path = tk.StringVar(value=str(Path(__file__).with_name("account.xlsx")))
        self.batch_running = False
        self.dungeon_limit = tk.StringVar(value="0")
        self.status = tk.StringVar(value="Mở instance, kết nối rồi chọn Script A, B hoặc C.")
        self.step_name = tk.StringVar(value="Chạm")
        self.steps: list[dict] = config.get("steps", [])
        self.capture_size = (0, 0)
        self.image_scale = 1
        self.image = None
        self.add_tap_pending = False
        self._build()
        self._refresh_steps()
        root.protocol("WM_DELETE_WINDOW", self._close)
        self.serial.trace_add("write", lambda *args: self._refresh_busy())
        root.after(100, self._drain_events)

    def _build(self) -> None:
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="Giả lập").grid(row=0, column=0, sticky="w")
        self.provider_combo = ttk.Combobox(top, textvariable=self.provider_name,
            values=[p.label for p in self.providers], state="readonly", width=14)
        self.provider_combo.grid(row=0, column=1, padx=6)
        self.provider_combo.bind("<<ComboboxSelected>>", self._provider_changed)
        self.open_emulator_button = ttk.Button(top, text=f"Mở {self.provider_name.get() or 'giả lập'}",
            command=self.open_instances, state="normal" if self.providers else "disabled")
        self.open_emulator_button.grid(row=0, column=2, padx=4)
        self.catalog_text = tk.StringVar(value="Đang quét instance…" if self.providers else "Chưa tìm thấy MuMu hoặc LDPlayer.")
        ttk.Label(top, textvariable=self.catalog_text).grid(row=0, column=3, columnspan=4, padx=10, sticky="w")
        ttk.Label(top, text="Thiết bị ADB").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(top, textvariable=self.serial, width=23).grid(row=1, column=1, padx=6, pady=(8, 0))
        ttk.Button(top, text="Kết nối", command=self.connect_async).grid(row=1, column=2, padx=4, pady=(8, 0))
        ttk.Label(top, text="Gói game").grid(row=1, column=3, padx=(15, 0), pady=(8, 0))
        ttk.Entry(top, textvariable=self.package, width=24).grid(row=1, column=4, padx=5, pady=(8, 0))
        ttk.Button(top, text="Tìm ứng dụng", command=self.find_packages).grid(row=1, column=5, pady=(8, 0))
        ttk.Button(top, text="Dùng game đang mở", command=self.use_foreground).grid(row=1, column=6, padx=5, pady=(8, 0))
        self._scan_catalog()

        ttk.Label(top, text="Thao tác trên").grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.target_name = tk.StringVar()
        self.target_sessions = []
        self.target_combo = ttk.Combobox(top, textvariable=self.target_name, state="readonly", width=38)
        self.target_combo.grid(row=2, column=1, columnspan=3, sticky="w", padx=6, pady=(8, 0))
        self.target_combo.bind("<<ComboboxSelected>>", self._target_changed)
        ttk.Label(top, text="Mỗi instance có tác vụ và điều khiển dừng riêng").grid(row=2, column=4, columnspan=3, sticky="w", pady=(8, 0))

        excel = ttk.LabelFrame(self.root, text="Tài khoản Excel", padding=9)
        excel.pack(fill="x", padx=10)
        ttk.Label(excel, text="Tệp Excel").grid(row=0, column=0, sticky="w")
        ttk.Entry(excel, textvariable=self.excel_path, width=73).grid(row=0, column=1, columnspan=3, padx=8, sticky="ew")
        ttk.Button(excel, text="Chọn tệp…", command=self.choose_excel).grid(row=0, column=4)
        self.script_buttons = []
        for col, script in enumerate(("A", "B", "C")):
            button = ttk.Button(excel, text=f"Script {script}", command=lambda name=script: self.run_excel_script(name))
            button.grid(row=1, column=col, padx=(0, 8), pady=(8, 0))
            self.script_buttons.append(button)
        ttk.Label(excel, text="A: ngày 1 · B: ngày tiếp theo 2–15 · C: hoàn thành ≥ 2 ngày").grid(row=1, column=3, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(excel, text="Chạy trên các instance đã kết nối · Hết tài khoản sẽ tự tắt instance").grid(row=2, column=0, columnspan=5, sticky="w", pady=(6, 0))
        dungeon = ttk.LabelFrame(self.root, text="Cỗ Máy Thời Gian · Phó Bản", padding=8)
        dungeon.pack(fill="x", padx=10, pady=(8, 0))
        self.dungeon_button = ttk.Button(dungeon, text="Tự động vượt phó bản", command=self.run_dungeon)
        self.dungeon_button.pack(side="left")
        ttk.Label(dungeon, text="Dừng sau số ải thắng:").pack(side="left", padx=(16, 5))
        ttk.Spinbox(dungeon, from_=0, to=999, width=5, textvariable=self.dungeon_limit).pack(side="left")
        ttk.Label(dungeon, text="0 = chạy đến khi thua · Dùng phiên game đang mở").pack(side="left", padx=12)

        equipment = ttk.Frame(self.root, padding=(10, 8, 10, 0))
        equipment.pack(fill="x")
        self.equipment_button = ttk.Button(equipment, text="Trang bị + Cường hóa toàn đội", command=self.run_equipment)
        self.equipment_button.pack(side="left")
        ttk.Label(equipment, text="Cỗ Máy Thời Gian · Tối đa 6 tướng · Lưu kết quả từng tướng").pack(side="left", padx=12)

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
        ttk.Button(foot, text="Dừng sau bước hiện tại", command=self.stop_current).pack(side="left", padx=8)
        ttk.Label(foot, textvariable=self.status, wraplength=850).pack(side="left", padx=12)

    def _close(self) -> None:
        self.stop_event.set()
        self.sessions.stop_all()
        if self.launch_control:
            self.launch_control.cancelled.set()
        self.root.destroy()

    def choose_excel(self):
        if self.batch_running:
            return
        path = filedialog.askopenfilename(title="Chọn danh sách tài khoản", filetypes=[("Excel", "*.xlsx")])
        if path:
            self.excel_path.set(path)

    def run_excel_script(self, script):
        if self.batch_running:
            self.status.set("Đang chạy một script; hãy chờ hoặc dừng các instance trước.")
            return
        sessions = self.sessions.connected()
        if not sessions:
            self.status.set("Hãy mở và kết nối ít nhất một instance trước.")
            return
        if any(session.active for session in sessions):
            self.status.set("Có instance đang chạy tác vụ; hãy chờ hoặc dừng trước khi chọn script.")
            return
        try:
            workbook = AccountWorkbook(self.excel_path.get().strip())
        except Exception as exc:
            messagebox.showerror("Excel", f"Không mở/ghi được Excel. Hãy đóng tệp trong Excel rồi thử lại.\n{exc}")
            return
        started = []
        for session in sessions:
            if not session.begin():
                for previous in started:
                    previous.finish('Sẵn sàng')
                self.status.set("Instance vừa nhận tác vụ khác; chưa bắt đầu script.")
                return
            started.append(session)
        package = self.package.get().strip() or PACKAGE
        self.batch_running = True
        for button in self.script_buttons:
            button.configure(state='disabled')
        def progress(session, message):
            self.events.put(('device_progress', (session, message), None))
        def cycle(session):
            connect(*session.connection)
            return ExcelCycle(session, run_adb, input_text, package,
                              lambda text: progress(session, text))
        batch = ScriptBatch(workbook, script, sessions, cycle,
                            lambda session: shutdown_session(session, run_adb), progress)
        def work():
            try:
                results = batch.run()
                self.events.put(('batch_done', results, None))
            except Exception as exc:
                for session in sessions:
                    session.finish('Lỗi điều phối')
                self.events.put(('batch_done', [{'error': str(exc), 'closed': False, 'completed': 0}], None))
        threading.Thread(target=work, daemon=True).start()
        self.status.set(f"Script {script} đang chạy trên {len(sessions)} instance.")
        self._refresh_busy()

    def run_dungeon(self) -> None:
        if self.busy:
            self.status.set("Đang thực hiện một thao tác khác.")
            return
        if not DungeonDetector().results_ready:
            messagebox.showinfo("Phó bản · thiếu tệp nhận diện", "Bộ ảnh nhận diện phó bản chưa đầy đủ. Hãy khôi phục thư mục assets/dungeon từ bản tool đầy đủ rồi mở lại.")
            return
        try:
            limit = int(self.dungeon_limit.get())
            if limit < 0:
                raise ValueError()
        except ValueError:
            messagebox.showinfo("Phó bản", "Số ải thắng phải là số nguyên từ 0 trở lên. Nhập 0 để chạy đến khi thua.")
            return
        serial = self.serial.get().strip()
        package = self.package.get().strip() or PACKAGE
        adb = self.adb
        session = self.sessions.device(adb, serial)
        control = session.control
        def emit(kind, value):
            self.events.put(("device_" + kind, (session, value), None))

        def work():
            connect(adb, serial)
            if foreground_package(adb, serial) != package:
                raise AdbError("Hãy mở OMG 3Q và vào nhân vật muốn chạy phó bản trước.")
            device = AdbDevice(adb, serial, run_adb, input_text, package)
            engine = DungeonEngine(device, stop=control.cancelled, clock=control.clock, sleeper=control.sleep,
                                   progress=lambda text: emit("progress", text),
                                   preview=lambda png: emit("frame", png))
            return engine.run(max_wins=limit)

        self._worker(work, self._dungeon_complete)

    def _dungeon_complete(self, result) -> None:
        self.last_dungeon_result = result
        self.status.set(result.message)
        if result.status in {"error", "unknown", "timeout", "needs_samples", "existing_result"}:
            messagebox.showwarning("Phó bản đã dừng", result.message +
                                   (f"\nẢnh kiểm tra: {result.screenshot}" if result.screenshot else ""))

    @property
    def busy(self):
        if hasattr(self, "sessions") and hasattr(self, "serial"):
            return self.sessions.device(self.adb, self.serial.get().strip()).active
        return getattr(self, "_manual_busy", False)

    @busy.setter
    def busy(self, value):
        self._manual_busy = value

    def _refresh_busy(self):
        value = self.busy
        self.dungeon_button.configure(state="disabled" if value else "normal")
        self.equipment_button.configure(state="disabled" if value else "normal")

    def _set_busy(self, value, message=None):
        self._refresh_busy()
        if message:
            self.status.set(message)

    def stop_current(self):
        self.sessions.device(self.adb, self.serial.get().strip()).control.cancelled.set()
        self.status.set("Đang dừng tác vụ trên instance đang chọn sau lệnh hiện tại.")

    def _refresh_targets(self):
        current = self.sessions.device(self.adb, self.serial.get().strip())
        self.target_sessions = [session for session in self.sessions.connected()
                                if session.name != "Thiết bị đang chọn"]
        self.target_combo.configure(values=[session.name for session in self.target_sessions])
        if current in self.target_sessions:
            self.target_combo.current(self.target_sessions.index(current))
        elif self.target_sessions and not current.active:
            self.target_combo.current(0)
            self._target_changed()

    def _target_changed(self, event=None):
        index = self.target_combo.current()
        if 0 <= index < len(self.target_sessions):
            session = self.target_sessions[index]
            self.adb, serial = session.connection
            self.serial.set(serial)
            self.status.set(session.name + " · " + session.state())
            self._refresh_busy()

    def run_equipment(self) -> None:
        if self.busy:
            self.status.set("Đang thực hiện một thao tác khác.")
            return
        if not EquipmentDetector().ready:
            messagebox.showinfo("Trang bị", "Thiếu bộ ảnh assets/equipment. Hãy khôi phục bộ tool đầy đủ.")
            return
        serial, package = self.serial.get().strip(), self.package.get().strip() or PACKAGE
        adb = self.adb
        session = self.sessions.device(adb, serial)
        control = session.control
        def emit(kind, value):
            self.events.put(("device_" + kind, (session, value), None))

        def work():
            connect(adb, serial)
            if foreground_package(adb, serial) != package:
                raise AdbError("Hãy mở OMG 3Q và vào sảnh Cỗ Máy Thời Gian hoặc Đội Hình trước.")
            device = AdbDevice(adb, serial, run_adb, input_text, package)
            skill = TeamEquipmentSkill(device, stop=control.cancelled, clock=control.clock, sleeper=control.sleep,
                                   progress=lambda text: emit("progress", text),
                                   preview=lambda png: emit("frame", png))
            return skill.run()

        self._worker(work, self._equipment_complete)

    def _equipment_complete(self, result) -> None:
        self.last_equipment_result = result
        self.status.set(result.message)
        if result.status in {"error", "blocked", "needs_samples"}:
            messagebox.showwarning("Skill trang bị đã dừng", result.message +
                                   (f"\nẢnh kiểm tra: {result.screenshot}" if result.screenshot else ""))

    def _worker(self, func, done=None):
        if not self.adb:
            try:
                self.adb = find_adb()
            except AdbError as exc:
                messagebox.showerror("ADB", str(exc))
                return
        session = self.sessions.device(self.adb, self.serial.get().strip())
        if not session.begin():
            self.status.set("Instance này đang có tác vụ; hãy chọn instance khác ở ô Thao tác trên.")
            return
        self._refresh_busy()
        def runner():
            result, error = None, None
            try:
                with active_session(session):
                    result = func()
                session.finish(getattr(result, "message", "Đã hoàn tất"))
            except InterruptedError:
                session.finish("Đã dừng tác vụ")
            except Exception as exc:
                error = str(exc)
                session.finish("Lỗi: " + error)
            self.events.put(("task_done", (session, result, error), done))
        threading.Thread(target=runner, daemon=True).start()

    def _drain_events(self) -> None:
        try:
            while True:
                kind, value, done = self.events.get_nowait()
                if kind == "batch_done":
                    self.batch_running = False
                    for button in self.script_buttons:
                        button.configure(state='normal')
                    self._refresh_busy()
                    errors = [r['error'] for r in value if r.get('error')]
                    completed = sum(r.get('completed', 0) for r in value)
                    message = "Đã xong" if not errors and all(r.get('closed') for r in value) else f"Đã kết thúc · hoàn thành {completed} tài khoản. " + " · ".join(errors)
                    self.status.set(message)
                    messagebox.showinfo('Script Excel', message)
                elif kind == "instance_ready":
                    self._refresh_targets()
                    self._refresh_busy()
                elif kind == "session_changed":
                    self._refresh_busy()
                elif kind in {"device_progress", "device_frame"}:
                    session, payload = value
                    if kind == "device_progress":
                        session.status = payload
                    if session is self.sessions.device(self.adb, self.serial.get().strip()):
                        if kind == "device_progress":
                            session.status = payload
                            self.status.set(session.name + " · " + payload)
                        else:
                            self._show_image(payload, update_status=False)
                elif kind == "task_done":
                    session, result, error = value
                    self._refresh_busy()
                    if session is self.sessions.device(self.adb, self.serial.get().strip()):
                        if error:
                            self.status.set(session.name + " · " + error)
                            messagebox.showerror("OMG 3Q", error)
                        elif done and result is not None:
                            done(result)
                        else:
                            self.status.set(session.name + " · " + session.state())
                elif kind == "catalog":
                    name, text = value
                    if self.provider_name.get() == name:
                        self.catalog_text.set(text)
                elif kind == "progress":
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
        adb, serial = self.adb, self.serial.get().strip()
        self._worker(lambda: connect(adb, serial),
                     lambda size: self.status.set(f"Đã kết nối giả lập · {size[0]}×{size[1]}"))

    def _provider_changed(self, event=None):
        provider = next((p for p in self.providers if p.label == self.provider_name.get()), None)
        if provider and not self.sessions.connected():
            self.adb = str(provider.adb)
        self.open_emulator_button.configure(text=f"Mở {self.provider_name.get()}")
        self._scan_catalog()

    def _scan_catalog(self):
        name = self.provider_name.get()
        self.active_provider_name = name
        provider = next((p for p in self.providers if p.label == name), None)
        if not provider:
            return
        self.catalog_text.set("Đang quét instance…")
        def work():
            try:
                text = f"{len(provider.instances())} instance có sẵn · Tự mở OMG 3Q sau khởi động"
            except Exception as exc:
                text = f"Chưa quét được instance: {exc}"
            self.events.put(("catalog", (name, text), None))
        threading.Thread(target=work, daemon=True).start()

    def open_instances(self):
        if self.instance_dialog and self.instance_dialog.window.winfo_exists():
            self.instance_dialog.window.lift()
            return
        provider = next((p for p in self.providers if p.label == self.provider_name.get()), None)
        if provider:
            self.instance_dialog = InstanceDialog(self, provider)
            self.provider_combo.configure(state="disabled")

    def start_mumu(self):
        self.provider_name.set("MuMu")
        self.open_instances()

    def start_ldmultiplayer(self):
        self.provider_name.set("LDPlayer")
        self.open_instances()

    def capture_async(self) -> None:
        adb, serial = self.adb, self.serial.get().strip()
        self._worker(lambda: screenshot(adb, serial), self._show_image)

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
        adb, serial = self.adb, self.serial.get().strip()
        self._worker(lambda: installed_packages(adb, serial), self._show_packages)

    def use_foreground(self) -> None:
        adb, serial = self.adb, self.serial.get().strip()
        self._worker(lambda: foreground_package(adb, serial), self._set_foreground)

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

    def run_steps(self) -> None:
        if not self.steps:
            messagebox.showinfo("Chưa có bước", "Hãy tạo các bước đăng nhập trước.")
            return
        serial = self.serial.get().strip()
        package = self.package.get().strip()
        steps = [step.copy() for step in self.steps]
        if any(step.get("action") in {"username", "password"} for step in steps):
            messagebox.showinfo("Excel", "Đăng nhập từ Excel bằng Script A, B hoặc C.")
            return
        adb = self.adb
        session = self.sessions.device(adb, serial)
        control = session.control
        def emit(kind, value):
            self.events.put(("device_" + kind, (session, value), None))

        def work():
            width, height = connect(adb, serial)
            for i, step in enumerate(steps, 1):
                control.checkpoint()
                if control.cancelled.is_set():
                    return "Đã dừng."
                capture_screen(adb, serial, run_adb, sleeper=control.sleep)
                action = step.get("action")
                emit("progress", f"Bước {i}/{len(steps)}: {self._describe(step)}")
                if action == "launch":
                    if not package:
                        raise AdbError("Chưa chọn gói game. Dùng nút 'Tìm ứng dụng'.")
                    launch_game(adb, serial, package)
                elif action == "tap":
                    sw, sh = int(step["width"]), int(step["height"])
                    if sw <= 0 or sh <= 0:
                        raise AdbError("Kích thước ảnh trong bước chạm không hợp lệ.")
                    x = min(width - 1, round(int(step["x"]) * width / sw))
                    y = min(height - 1, round(int(step["y"]) * height / sh))
                    tap(adb, serial, x, y)
                elif action == "wait":
                    end = control.clock() + float(step["seconds"])
                    while control.clock() < end:
                        control.sleep(min(0.2, max(0, end - control.clock())))
                        if control.cancelled.is_set():
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
