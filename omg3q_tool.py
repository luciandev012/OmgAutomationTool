"""MuMu Player 12 automation for OMG 3Q. Run with the project's virtual environment."""

from __future__ import annotations

import os
import queue
import re
import shlex
import shutil
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from login_engine import AdbDevice, PACKAGE
from account_excel import AccountWorkbook
from excel_scripts import ExcelCycle, ScriptBatch, shutdown_session
from dungeon_engine import DungeonDetector, DungeonEngine
from equipment_skill import EquipmentDetector, TeamEquipmentSkill
from emulator_instances import detect_emulators
from instance_dialog import InstanceDialog
from task_sessions import SessionRegistry, active_session, guard_command
from advance_skill import AdvanceDetector, AdvanceSkill, TeamAdvanceSkill
from level_skill import LevelDetector, LevelSkill, TeamLevelSkill
from treasure_skill import TreasureDetector, TreasureSkill, TeamTreasureSkill
from evolution_skill import EvolutionDetector, EvolutionSkill, TeamEvolutionSkill, KINDS
from chest_skill import ChestDetector, ChestSkill
from daily_tasks_skill import DailyTasksSkill
from trial_skill import TrialSkill
from cross_server_skill import CrossServerSkill
from beast_skill import BeastSkill
from team_arena_skill import TeamArenaSkill
from assistant_skill import AssistantSkill
from fragment_skill import FragmentSweepSkill


TITLE = "OMG 3Q · Công cụ tự động hóa"
DEFAULT_ADB = Path(r"C:\Program Files\Netease\MuMuPlayer\nx_main\adb.exe")
DEFAULT_MANAGER = Path(r"C:\Program Files\Netease\MuMuPlayer\nx_main\MuMuManager.exe")


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
        raise AdbError("Tên gói ứng dụng không hợp lệ.")
    reply = run_adb(adb, "-s", serial, "shell", "monkey", "-p", package, "1")
    if b"No activities found" in reply or b"Events injected: 0" in reply:
        raise AdbError(f"Không mở được ứng dụng {package}.")


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
    raise AdbError("Chưa nhận ra game đang mở. Hãy vào OMG 3Q rồi thử lại.")


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title(TITLE)
        root.geometry(f"1230x{max(700,min(980,root.winfo_screenheight()-100))}")
        root.minsize(1020, 700)
        self.events: queue.Queue = queue.Queue()
        self.sessions = SessionRegistry()
        self.busy = False
        # The instance manager can be opened even when MuMu ADB is absent.
        try:
            self.adb = find_adb()
        except AdbError:
            self.adb = ""
        self.providers = detect_emulators(DEFAULT_MANAGER, find_ldmultiplayer())
        self.provider_name = tk.StringVar(value=self.providers[0].label if self.providers else "")
        self.instance_dialog = None
        if self.providers:
            self.adb = str(self.providers[0].adb)
        self.serial = tk.StringVar(value="")
        self.excel_path = tk.StringVar(value=str(Path(__file__).with_name("account.xlsx")))
        self.batch_running = False
        self.dungeon_limit = tk.StringVar(value="0")
        self.dungeon_spam = tk.BooleanVar(value=False)
        self.dungeon_spam_limit = tk.StringVar(value="100")
        self.advance_scope = tk.StringVar(value="Tướng đang chọn")
        self.advance_mode = tk.StringVar(value="Tự dừng khi không thể")
        self.advance_target = tk.StringVar(value="10")
        self.level_scope = tk.StringVar(value="Tướng đang chọn")
        self.level_mode = tk.StringVar(value="Tự dừng khi không thể")
        self.level_target = tk.StringVar(value="100")
        self.treasure_scope = tk.StringVar(value="Tướng đang chọn")
        self.treasure_mode = tk.StringVar(value="Tự dừng khi không thể")
        self.treasure_target = tk.StringVar(value="10")
        self.evolution = {kind: {
            "scope": tk.StringVar(value="Tướng đang chọn"),
            "mode": tk.StringVar(value="Tự dừng khi không thể"),
            "target": tk.StringVar(value="1"), "lv": tk.StringVar(value="0")}
            for kind in KINDS}
        self.status = tk.StringVar(value="Mở instance, kết nối rồi chọn Script A, B hoặc C.")
        self._build()
        self._refresh_busy()
        root.update_idletasks()
        root.minsize(820, root.winfo_reqheight())
        root.geometry("")  # Fit the initial window to its contents.
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
        ttk.Label(top, textvariable=self.catalog_text, wraplength=340).grid(row=0, column=3, columnspan=4, padx=10, sticky="w")
        self._scan_catalog()

        ttk.Label(top, text="Thao tác trên").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.target_name = tk.StringVar()
        self.target_sessions = []
        self.target_combo = ttk.Combobox(top, textvariable=self.target_name, state="readonly", width=38)
        self.target_combo.grid(row=1, column=1, columnspan=3, sticky="w", padx=6, pady=(8, 0))
        self.target_combo.bind("<<ComboboxSelected>>", self._target_changed)
        ttk.Label(top, text="Mỗi instance có tác vụ và điều khiển dừng riêng", wraplength=280).grid(row=1, column=4, columnspan=3, sticky="w", pady=(8, 0))

        excel = ttk.LabelFrame(self.root, text="Tài khoản Excel", padding=9)
        excel.pack(fill="x", padx=10)
        excel.columnconfigure(3, weight=1)
        ttk.Label(excel, text="Tệp Excel").grid(row=0, column=0, sticky="w")
        ttk.Entry(excel, textvariable=self.excel_path, width=40).grid(row=0, column=1, columnspan=3, padx=8, sticky="ew")
        ttk.Button(excel, text="Chọn tệp…", command=self.choose_excel).grid(row=0, column=4)
        self.script_buttons = []
        for col, script in enumerate(("A", "B", "C")):
            button = ttk.Button(excel, text=f"Script {script}", command=lambda name=script: self.run_excel_script(name))
            button.grid(row=1, column=col, padx=(0, 8), pady=(8, 0))
            self.script_buttons.append(button)
        ttk.Label(excel, text="A: ngày 1 · B: ngày tiếp theo 2–15 · C: hoàn thành ≥ 2 ngày").grid(row=1, column=3, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(excel, text="Chạy trên các instance đã kết nối · Hết tài khoản sẽ tự tắt instance").grid(row=2, column=0, columnspan=5, sticky="w", pady=(6, 0))
        self.excel_test_button = ttk.Button(excel, text="Test Excel · 2 MuMu × 3 lượt", command=self.run_excel_login_test)
        self.excel_test_button.grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Label(excel, text="3 lượt/máy · Giữ X/V để kiểm tra").grid(row=3, column=3, columnspan=2, sticky="w", pady=(8, 0))
        daily = ttk.LabelFrame(self.root, text="Sảnh chính · Nhiệm vụ hằng ngày", padding=8)
        daily.pack(fill="x", padx=10, pady=(8, 0))
        daily_navigation = ttk.Frame(daily)
        daily_navigation.pack(fill="x")
        self.daily_tasks_button = ttk.Button(daily_navigation, text="Mở nhiệm vụ hằng ngày", command=self.run_daily_tasks)
        self.daily_tasks_button.pack(side="left")
        self.soul_hunt_button = ttk.Button(daily_navigation, text="Liệp Hồn 500 lần + Hồn Tướng", command=self.run_soul_hunt)
        self.soul_hunt_button.pack(side="left", padx=(8, 0))
        self.assistant_button = ttk.Button(daily_navigation, text="Trợ thủ · 5 tab", command=self.run_assistant)
        self.assistant_button.pack(side="left", padx=(8, 0))
        self.fragment_button = ttk.Button(daily_navigation, text="Quét mảnh Điển Vi", command=self.run_fragment_sweep)
        self.fragment_button.pack(side="left", padx=(8, 0))
        daily_combat = ttk.Frame(daily)
        daily_combat.pack(fill="x", pady=(6, 0))
        self.trial_buttons = []
        for kind, label in (("phi", "Thí Luyện Phi Thăng"), ("ma", "Thí Luyện Ma Động")):
            button = ttk.Button(daily_combat, text=label, command=lambda kind=kind: self.run_trial(kind))
            button.pack(side="left", padx=(8, 0))
            self.trial_buttons.append(button)
        self.cross_server_button = ttk.Button(daily_combat, text="Tỉ Võ Liên Server", command=self.run_cross_server)
        self.cross_server_button.pack(side="left", padx=(8, 0))
        self.beast_button = ttk.Button(daily_combat, text="Thần Thú Động", command=self.run_beast)
        self.beast_button.pack(side="left", padx=(8, 0))
        self.team_arena_button = ttk.Button(daily_combat, text="Quần Anh Tranh Bá", command=self.run_team_arena)
        self.team_arena_button.pack(side="left", padx=(8, 0))

        dungeon = ttk.LabelFrame(self.root, text="Cỗ Máy Thời Gian · Phó Bản · Sao tối + dấu kiếm", padding=8)
        dungeon.pack(fill="x", padx=10, pady=(8, 0))
        dungeon_row = ttk.Frame(dungeon)
        dungeon_row.pack(fill="x")
        self.dungeon_button = ttk.Button(dungeon_row, text="Tự động vượt phó bản", command=self.run_dungeon)
        self.dungeon_button.pack(side="left")
        ttk.Label(dungeon_row, text="Dừng sau số ải thắng:").pack(side="left", padx=(16, 5))
        self.dungeon_limit_entry = ttk.Spinbox(dungeon_row, from_=0, to=999, width=5, textvariable=self.dungeon_limit)
        self.dungeon_limit_entry.pack(side="left")
        self.dungeon_spam_check = ttk.Checkbutton(dungeon_row, text="Spam khi thua",
            variable=self.dungeon_spam, command=self._dungeon_controls)
        self.dungeon_spam_check.pack(side="left", padx=(16, 5))
        ttk.Label(dungeon_row, text="Số lần/ải:").pack(side="left", padx=(5, 5))
        self.dungeon_spam_entry = ttk.Spinbox(dungeon_row, from_=1, to=9999, width=6,
            textvariable=self.dungeon_spam_limit)
        self.dungeon_spam_entry.pack(side="left")
        ttk.Label(dungeon, text="0 = không giới hạn ải thắng · Spam tính các trận đánh lại, đặt lại khi thắng · Hết lượt sẽ hỏi chạy lượt mới").pack(anchor="w", pady=(4, 0))
        self._dungeon_controls()

        equipment = ttk.Frame(self.root, padding=(10, 8, 10, 0))
        equipment.pack(fill="x")
        self.equipment_button = ttk.Button(equipment, text="Trang bị + Cường hóa toàn đội", command=self.run_equipment)
        self.equipment_button.pack(side="left")
        ttk.Label(equipment, text="Cỗ Máy Thời Gian · Tối đa 6 tướng · Lưu kết quả từng tướng").pack(side="left", padx=12)

        advance = ttk.LabelFrame(self.root, text="Cỗ Máy Thời Gian · Tiến cấp tướng", padding=8)
        advance.pack(fill="x", padx=10, pady=(8, 0))
        self.advance_button = ttk.Button(advance, text="Tiến cấp tướng", command=self.run_advance)
        self.advance_button.pack(side="left")
        self.advance_scope_combo = ttk.Combobox(advance, textvariable=self.advance_scope, state="readonly",
            values=("Tướng đang chọn", "Toàn đội tối đa 6 tướng"), width=24)
        self.advance_scope_combo.pack(side="left", padx=8)
        self.advance_mode_combo = ttk.Combobox(advance, textvariable=self.advance_mode, state="readonly",
            values=("Tự dừng khi không thể", "Dừng ở bậc mục tiêu"), width=24)
        self.advance_mode_combo.pack(side="left", padx=4)
        self.advance_mode_combo.bind("<<ComboboxSelected>>", lambda event: self._advance_controls())
        ttk.Label(advance, text="Bậc +").pack(side="left", padx=(8, 3))
        self.advance_target_entry = ttk.Entry(advance, textvariable=self.advance_target, width=5)
        self.advance_target_entry.pack(side="left")
        self._advance_controls()

        level = ttk.LabelFrame(self.root, text="Cỗ Máy Thời Gian · Tăng cấp tướng", padding=8)
        level.pack(fill="x", padx=10, pady=(8, 0))
        self.level_button = ttk.Button(level, text="Tăng cấp tướng", command=self.run_level)
        self.level_button.pack(side="left")
        self.level_scope_combo = ttk.Combobox(level, textvariable=self.level_scope, state="readonly",
            values=("Tướng đang chọn", "Toàn đội tối đa 6 tướng"), width=24)
        self.level_scope_combo.pack(side="left", padx=8)
        self.level_mode_combo = ttk.Combobox(level, textvariable=self.level_mode, state="readonly",
            values=("Tự dừng khi không thể", "Dừng ở cấp mục tiêu"), width=24)
        self.level_mode_combo.pack(side="left", padx=4)
        self.level_mode_combo.bind("<<ComboboxSelected>>", lambda event: self._level_controls())
        ttk.Label(level, text="Cấp").pack(side="left", padx=(8, 3))
        self.level_target_entry = ttk.Entry(level, textvariable=self.level_target, width=5)
        self.level_target_entry.pack(side="left")
        self._level_controls()

        treasure = ttk.LabelFrame(self.root, text="Cỗ Máy Thời Gian · Cường hóa bảo vật", padding=8)
        treasure.pack(fill="x", padx=10, pady=(8, 0))
        self.treasure_button = ttk.Button(treasure, text="Cường hóa bảo vật", command=self.run_treasure)
        self.treasure_button.pack(side="left")
        self.treasure_scope_combo = ttk.Combobox(treasure, textvariable=self.treasure_scope, state="readonly",
            values=("Tướng đang chọn", "Toàn đội tối đa 6 tướng"), width=24)
        self.treasure_scope_combo.pack(side="left", padx=8)
        self.treasure_mode_combo = ttk.Combobox(treasure, textvariable=self.treasure_mode, state="readonly",
            values=("Tự dừng khi không thể", "Dừng ở bậc mục tiêu"), width=24)
        self.treasure_mode_combo.pack(side="left", padx=4)
        self.treasure_mode_combo.bind("<<ComboboxSelected>>", lambda event: self._treasure_controls())
        ttk.Label(treasure, text="Bậc +").pack(side="left", padx=(8, 3))
        self.treasure_target_entry = ttk.Entry(treasure, textvariable=self.treasure_target, width=5)
        self.treasure_target_entry.pack(side="left")
        self._treasure_controls()

        evolution = ttk.LabelFrame(self.root, text="Cỗ Máy Thời Gian · Đột Phá / Giác Tỉnh", padding=8)
        evolution.pack(fill="x", padx=10, pady=(8, 0))
        self.evolution_widgets = {}
        for kind, label in KINDS.items():
            row = ttk.Frame(evolution)
            row.pack(fill="x", pady=2)
            data = self.evolution[kind]
            button = ttk.Button(row, text=label + " tướng", command=lambda k=kind: self.run_evolution(k))
            button.pack(side="left")
            scope = ttk.Combobox(row, textvariable=data["scope"], state="readonly", width=24,
                values=("Tướng đang chọn", "Toàn đội tối đa 6 tướng"))
            scope.pack(side="left", padx=8)
            mode = ttk.Combobox(row, textvariable=data["mode"], state="readonly", width=24,
                values=("Tự dừng khi không thể", "Dừng ở bậc mục tiêu"))
            mode.pack(side="left", padx=4)
            mode.bind("<<ComboboxSelected>>", lambda event: self._evolution_controls())
            ttk.Label(row, text="Đỏ-Bậc" if kind == "breakthrough" else "Sao").pack(side="left", padx=(8,3))
            target = ttk.Entry(row, textvariable=data["target"], width=4)
            target.pack(side="left")
            inputs = [target]
            if kind == "awakening":
                ttk.Label(row, text="Lv").pack(side="left", padx=(8,3))
                lv = ttk.Entry(row, textvariable=data["lv"], width=4)
                lv.pack(side="left")
                inputs.append(lv)
            self.evolution_widgets[kind] = (button,scope,mode,inputs)
        self._evolution_controls()

        chest = ttk.LabelFrame(self.root, text="Cỗ Máy Thời Gian · Rương", padding=8)
        chest.pack(fill="x", padx=10, pady=(8, 0))
        self.chest_button = ttk.Button(chest, text="Mở hết 4 loại rương", command=self.run_chest)
        self.chest_button.pack(side="left")
        ttk.Label(chest, text="Tự tăng level khi đủ EXP · Dừng khi hết rương hoặc không thể mở").pack(side="left", padx=12)

        foot = ttk.Frame(self.root, padding=(10, 12, 10, 10))
        foot.pack(fill="x")
        ttk.Button(foot, text="Dừng sau bước hiện tại", command=self.stop_current).pack(side="left", padx=8)
        ttk.Label(foot, textvariable=self.status, wraplength=540).pack(side="left", padx=12)

    def _close(self) -> None:
        self.sessions.stop_all()
        self.root.destroy()

    def choose_excel(self):
        if self.batch_running:
            return
        path = filedialog.askopenfilename(title="Chọn danh sách tài khoản", filetypes=[("Excel", "*.xlsx")])
        if path:
            self.excel_path.set(path)

    def run_excel_login_test(self):
        if self.batch_running or any(s.active for s in self.sessions.connected()):
            self.status.set("Đang có tác vụ; hãy dừng trước khi test.")
            return
        provider = next((p for p in self.providers if p.kind == 'mumu'), None)
        if provider is None:
            self.status.set("Chưa tìm thấy MuMu.")
            return
        try:
            from excel_login_test import ExcelLoginTest
            test = ExcelLoginTest(self.sessions, provider, self.excel_path.get().strip(),
                run_adb, input_text, launch_game,
                lambda session, text: self.events.put(('device_progress', (session, text), None)),
                wait_forever=getattr(self, '_test_wait_forever', False),
                rounds=getattr(self, '_test_rounds', 3),
                iteration_offset=getattr(self, '_test_iteration_offset', 0),
                **getattr(self, '_test_options', {}))
        except Exception as exc:
            messagebox.showerror("Test Excel", str(exc))
            return
        self._test_expected = test.rounds * (1 if test.instance_name else 2)
        self._test_wait_forever = False
        self._test_options = {}
        self.batch_running = True
        self.excel_test_button.configure(state='disabled')
        for button in self.script_buttons:
            button.configure(state='disabled')
        def work():
            try:
                results = test.run()
            except Exception:
                results = [{'completed': 0, 'error': 'Không hoàn tất phiên test; xem nhật ký.', 'closed': False}]
            self.events.put(('excel_test_done', results, None))
        threading.Thread(target=work, daemon=True).start()
        self.status.set(f"Test {test.instance_name or '2 MuMu'} × {test.rounds} lượt · " + ("không timeout" if test.wait_forever else "timeout mặc định") + " · Dừng từ hộp điều khiển instance.")


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
        package = PACKAGE
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

    def _dungeon_controls(self) -> None:
        self.dungeon_limit_entry.configure(state="disabled" if self.busy else "normal")
        self.dungeon_spam_check.configure(state="disabled" if self.busy else "normal")
        self.dungeon_spam_entry.configure(state="normal" if not self.busy and self.dungeon_spam.get() else "disabled")

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
            messagebox.showinfo("Phó bản", "Số ải thắng phải là số nguyên từ 0 trở lên. Nhập 0 để không giới hạn số ải thắng.")
            return
        spam = self.dungeon_spam.get()
        spam_limit = 100
        if spam:
            try:
                spam_limit = int(self.dungeon_spam_limit.get())
                if spam_limit < 1:
                    raise ValueError()
            except ValueError:
                messagebox.showinfo("Phó bản · Spam", "Số lần spam phải là số nguyên lớn hơn 0 (mặc định 100).")
                return
        serial = self.serial.get().strip()
        package = PACKAGE
        adb = self.adb
        session = self.sessions.device(adb, serial)
        control = session.control
        def emit(kind, value):
            self.events.put(("device_" + kind, (session, value), None))

        def work():
            connect(adb, serial)
            if foreground_package(adb, serial) != package:
                raise AdbError("Hãy mở OMG 3Q và vào nhân vật muốn chạy phó bản trước.")
            device = AdbDevice(adb, serial, run_adb, input_text, package, capture_options={"dismiss_hints": False})
            engine = DungeonEngine(device, stop=control.cancelled, clock=control.clock, sleeper=control.sleep,
                                   progress=lambda text: emit("progress", text))
            return engine.run(max_wins=limit, spam=spam, spam_limit=spam_limit)

        self._worker(work, self._dungeon_complete)

    def _dungeon_complete(self, result) -> None:
        self.last_dungeon_result = result
        self.status.set(result.message)
        if result.status == "spam_limit":
            again = messagebox.askyesno("Phó bản · Đã hết lượt spam", result.message +
                "\n\nChạy lượt spam mới với số lần đã cài đặt?\nChọn Không để dừng và giữ nguyên màn hình kết quả.",
                parent=self.root)
            if again:
                self.root.after_idle(self.run_dungeon)
        elif result.status in {"error", "unknown", "timeout", "needs_samples", "existing_result", "auto_unverified", "retry_unverified", "scan_unverified", "no_frontier"}:
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
        value = self.busy or not self.serial.get().strip()
        self.daily_tasks_button.configure(state="disabled" if value else "normal")
        self.soul_hunt_button.configure(state="disabled" if value else "normal")
        self.cross_server_button.configure(state="disabled" if value else "normal")
        self.beast_button.configure(state="disabled" if value else "normal")
        self.team_arena_button.configure(state="disabled" if value else "normal")
        self.assistant_button.configure(state="disabled" if value else "normal")
        self.fragment_button.configure(state="disabled" if value else "normal")
        for button in self.trial_buttons:
            button.configure(state="disabled" if value else "normal")
        self.dungeon_button.configure(state="disabled" if value else "normal")
        self._dungeon_controls()
        self.equipment_button.configure(state="disabled" if value else "normal")
        self._advance_controls()
        self._level_controls()
        self._treasure_controls()
        self._evolution_controls()
        self.chest_button.configure(state="disabled" if value else "normal")

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
        serial, package = self.serial.get().strip(), PACKAGE
        adb = self.adb
        session = self.sessions.device(adb, serial)
        control = session.control
        def emit(kind, value):
            self.events.put(("device_" + kind, (session, value), None))

        def work():
            connect(adb, serial)
            if foreground_package(adb, serial) != package:
                raise AdbError("Hãy mở OMG 3Q và vào sảnh Cỗ Máy Thời Gian hoặc Đội Hình trước.")
            device = AdbDevice(adb, serial, run_adb, input_text, package, capture_options={"dismiss_hints": False})
            skill = TeamEquipmentSkill(device, stop=control.cancelled, clock=control.clock, sleeper=control.sleep,
                                   progress=lambda text: emit("progress", text))
            return skill.run()

        self._worker(work, self._equipment_complete)

    def _equipment_complete(self, result) -> None:
        self.last_equipment_result = result
        self.status.set(result.message)
        if result.status in {"error", "blocked", "needs_samples"}:
            messagebox.showwarning("Skill trang bị đã dừng", result.message +
                                   (f"\nẢnh kiểm tra: {result.screenshot}" if result.screenshot else ""))

    def _advance_controls(self):
        self.advance_button.configure(state="disabled" if self.busy else "normal")
        for combo in (self.advance_scope_combo, self.advance_mode_combo):
            combo.configure(state="disabled" if self.busy else "readonly")
        active = self.advance_mode.get() == "Dừng ở bậc mục tiêu"
        self.advance_target_entry.configure(state="normal" if active and not self.busy else "disabled")

    def run_advance(self):
        if self.busy:
            self.status.set("Đang thực hiện một thao tác khác.")
            return
        if not AdvanceDetector().ready or not EquipmentDetector().ready:
            messagebox.showinfo("Tiến cấp", "Thiếu bộ ảnh nhận diện; hãy khôi phục assets/advance và assets/equipment.")
            return
        target = None
        if self.advance_mode.get() == "Dừng ở bậc mục tiêu":
            text = self.advance_target.get().strip()
            if not text.isascii() or not text.isdigit():
                messagebox.showinfo("Tiến cấp", "Nhập bậc mục tiêu là số nguyên từ 0 đến 999.")
                return
            target = int(text)
            try:
                AdvanceSkill.validate_target(target)
            except ValueError as exc:
                messagebox.showinfo("Tiến cấp", str(exc))
                return
        whole_team = self.advance_scope.get() == "Toàn đội tối đa 6 tướng"
        serial, package = self.serial.get().strip(), PACKAGE
        adb = self.adb
        session = self.sessions.device(adb, serial)
        control = session.control
        def emit(text):
            self.events.put(("device_progress", (session, text), None))

        def work():
            connect(adb, serial)
            if foreground_package(adb, serial) != package:
                raise AdbError("Hãy mở OMG 3Q và vào nhân vật trước.")
            device = AdbDevice(adb, serial, run_adb, input_text, package, capture_options={"dismiss_hints": False})
            skill_class = TeamAdvanceSkill if whole_team else AdvanceSkill
            skill = skill_class(device, stop=control.cancelled, clock=control.clock, sleeper=control.sleep,
                progress=emit)
            return skill.run(target_rank=target)

        self._worker(work, self._advance_complete)

    def _advance_complete(self, result):
        self.last_advance_result = result
        self.status.set(result.message)
        if result.status in {"error", "blocked", "needs_samples"}:
            messagebox.showwarning("Tiến cấp đã dừng", result.message +
                (f"\nẢnh kiểm tra: {result.screenshot}" if result.screenshot else ""))

    def _level_controls(self):
        self.level_button.configure(state="disabled" if self.busy else "normal")
        for combo in (self.level_scope_combo, self.level_mode_combo):
            combo.configure(state="disabled" if self.busy else "readonly")
        active = self.level_mode.get() == "Dừng ở cấp mục tiêu"
        self.level_target_entry.configure(state="normal" if active and not self.busy else "disabled")

    def run_level(self):
        if self.busy:
            self.status.set("Đang thực hiện một thao tác khác.")
            return
        if not LevelDetector().ready or not EquipmentDetector().ready:
            messagebox.showinfo("Tăng cấp", "Thiếu bộ ảnh nhận diện; hãy khôi phục assets/level và assets/equipment.")
            return
        target = None
        if self.level_mode.get() == "Dừng ở cấp mục tiêu":
            text = self.level_target.get().strip()
            if not text.isascii() or not text.isdigit():
                messagebox.showinfo("Tăng cấp", "Nhập cấp mục tiêu là số nguyên từ 0 đến 999.")
                return
            target = int(text)
            try:
                LevelSkill.validate_target(target)
            except ValueError as exc:
                messagebox.showinfo("Tăng cấp", str(exc))
                return
        whole_team = self.level_scope.get() == "Toàn đội tối đa 6 tướng"
        serial, package = self.serial.get().strip(), PACKAGE
        adb = self.adb
        session = self.sessions.device(adb, serial)
        control = session.control
        def emit(text):
            self.events.put(("device_progress", (session, text), None))

        def work():
            connect(adb, serial)
            if foreground_package(adb, serial) != package:
                raise AdbError("Hãy mở OMG 3Q và vào nhân vật trước.")
            device = AdbDevice(adb, serial, run_adb, input_text, package, capture_options={"dismiss_hints": False})
            skill_class = TeamLevelSkill if whole_team else LevelSkill
            skill = skill_class(device, stop=control.cancelled, clock=control.clock, sleeper=control.sleep,
                progress=emit)
            return skill.run(target_level=target)

        self._worker(work, self._level_complete)

    def _level_complete(self, result):
        self.last_level_result = result
        self.status.set(result.message)
        if result.status in {"error", "blocked", "needs_samples"}:
            messagebox.showwarning("Tăng cấp đã dừng", result.message +
                (f"\nẢnh kiểm tra: {result.screenshot}" if result.screenshot else ""))

    def _treasure_controls(self):
        self.treasure_button.configure(state="disabled" if self.busy else "normal")
        for combo in (self.treasure_scope_combo, self.treasure_mode_combo):
            combo.configure(state="disabled" if self.busy else "readonly")
        active = self.treasure_mode.get() == "Dừng ở bậc mục tiêu"
        self.treasure_target_entry.configure(state="normal" if active and not self.busy else "disabled")

    def run_treasure(self):
        if self.busy:
            self.status.set("Đang thực hiện một thao tác khác.")
            return
        if not TreasureDetector().ready or not EquipmentDetector().ready:
            messagebox.showinfo("Cường hóa bảo vật", "Thiếu bộ ảnh nhận diện; hãy khôi phục assets/treasure, assets/advance và assets/equipment.")
            return
        target = None
        if self.treasure_mode.get() == "Dừng ở bậc mục tiêu":
            text = self.treasure_target.get().strip()
            if not text.isascii() or not text.isdigit():
                messagebox.showinfo("Cường hóa bảo vật", "Nhập bậc mục tiêu là số nguyên từ 0 đến 999.")
                return
            target = int(text)
            try:
                TreasureSkill.validate_target(target)
            except ValueError as exc:
                messagebox.showinfo("Cường hóa bảo vật", str(exc))
                return
        whole_team = self.treasure_scope.get() == "Toàn đội tối đa 6 tướng"
        serial, package = self.serial.get().strip(), PACKAGE
        adb = self.adb
        session = self.sessions.device(adb, serial)
        control = session.control
        def emit(text):
            self.events.put(("device_progress", (session, text), None))

        def work():
            connect(adb, serial)
            if foreground_package(adb, serial) != package:
                raise AdbError("Hãy mở OMG 3Q và vào nhân vật trước.")
            device = AdbDevice(adb, serial, run_adb, input_text, package, capture_options={"dismiss_hints": False})
            skill_class = TeamTreasureSkill if whole_team else TreasureSkill
            skill = skill_class(device, stop=control.cancelled, clock=control.clock, sleeper=control.sleep,
                progress=emit)
            return skill.run(target_rank=target)

        self._worker(work, self._treasure_complete)

    def _treasure_complete(self, result):
        self.last_treasure_result = result
        self.status.set(result.message)
        if result.status in {"error", "blocked", "needs_samples"}:
            messagebox.showwarning("Cường hóa bảo vật đã dừng", result.message +
                (f"\nẢnh kiểm tra: {result.screenshot}" if result.screenshot else ""))

    def _evolution_controls(self):
        for kind, (button, scope, mode, inputs) in self.evolution_widgets.items():
            button.configure(state="disabled" if self.busy else "normal")
            for combo in (scope,mode):
                combo.configure(state="disabled" if self.busy else "readonly")
            active = self.evolution[kind]["mode"].get() == "Dừng ở bậc mục tiêu"
            for entry in inputs:
                entry.configure(state="normal" if active and not self.busy else "disabled")

    def run_evolution(self, kind):
        if self.busy:
            self.status.set("Đang thực hiện một thao tác khác.")
            return
        label = KINDS[kind]
        if not EvolutionDetector(kind).ready:
            messagebox.showinfo(label, "Thiếu bộ ảnh nhận diện " + label + ".")
            return
        data = self.evolution[kind]
        target = None
        if data["mode"].get() == "Dừng ở bậc mục tiêu":
            values = [data["target"].get().strip()]
            if kind == "awakening":
                values.append(data["lv"].get().strip())
            if any(not v.isascii() or not v.isdigit() or not 0 <= int(v) <= 999 for v in values):
                messagebox.showinfo(label, "Nhập mốc là số nguyên từ 0 đến 999.")
                return
            target = tuple(map(int,values))
        whole_team = data["scope"].get() == "Toàn đội tối đa 6 tướng"
        serial, package = self.serial.get().strip(), PACKAGE
        adb = self.adb
        session = self.sessions.device(adb, serial)
        control = session.control
        def emit(text):
            self.events.put(("device_progress", (session, text), None))

        def work():
            connect(adb,serial)
            if foreground_package(adb,serial) != package:
                raise AdbError("Hãy mở OMG 3Q và vào nhân vật trước.")
            device = AdbDevice(adb,serial,run_adb,input_text,package, capture_options={"dismiss_hints": False})
            skill_class = TeamEvolutionSkill if whole_team else EvolutionSkill
            skill = skill_class(device,kind=kind,stop=control.cancelled, clock=control.clock, sleeper=control.sleep,
                progress=emit)
            return skill.run(target_rank=target)

        self._worker(work,lambda result:self._evolution_complete(kind,result))

    def _evolution_complete(self,kind,result):
        setattr(self,"last_"+kind+"_result",result)
        self.status.set(result.message)
        if result.status in {"error","blocked","needs_samples"}:
            messagebox.showwarning(KINDS[kind]+" đã dừng", result.message +
                (f"\nẢnh kiểm tra: {result.screenshot}" if result.screenshot else ""))

    def run_daily_tasks(self):
        self._run_daily_action(DailyTasksSkill.run)

    def run_soul_hunt(self):
        self._run_daily_action(DailyTasksSkill.run_soul_hunt)

    def run_trial(self, kind):
        self._run_daily_action(lambda skill: skill.run_trial(kind=kind), TrialSkill)

    def run_cross_server(self):
        self._run_daily_action(CrossServerSkill.run_duels, CrossServerSkill)

    def run_beast(self):
        self._run_daily_action(BeastSkill.run_beast, BeastSkill)

    def run_team_arena(self):
        self._run_daily_action(TeamArenaSkill.run_arena, TeamArenaSkill)

    def run_assistant(self):
        self._run_daily_action(AssistantSkill.run_assistant, AssistantSkill)

    def run_fragment_sweep(self):
        self._run_daily_action(FragmentSweepSkill.run_sweep, FragmentSweepSkill)

    def _run_daily_action(self, action, skill_type=DailyTasksSkill):
        if self.busy:
            self.status.set("Đang thực hiện một thao tác khác.")
            return
        serial, package = self.serial.get().strip(), PACKAGE
        adb = self.adb
        session = self.sessions.device(adb, serial)
        control = session.control
        def emit(text):
            self.events.put(("device_progress", (session, text), None))

        def work():
            connect(adb, serial)
            if foreground_package(adb, serial) != package:
                raise AdbError("Hãy mở OMG 3Q và vào sảnh chính trước.")
            device = AdbDevice(adb, serial, run_adb, input_text, package, capture_options={"dismiss_hints": False})
            skill = skill_type(device, stop=control.cancelled, clock=control.clock, sleeper=control.sleep,
                progress=emit)
            return action(skill)

        self._worker(work, self._daily_tasks_complete)

    def _daily_tasks_complete(self, result):
        self.last_daily_tasks_result = result
        self.status.set(result.message)
        if result.status in {"error", "blocked", "needs_samples"}:
            messagebox.showwarning("Nhiệm vụ hằng ngày đã dừng", result.message +
                (f"\nẢnh kiểm tra: {result.screenshot}" if result.screenshot else ""))

    def run_chest(self):
        if self.busy:
            self.status.set("Đang thực hiện một thao tác khác.")
            return
        if not ChestDetector().ready:
            messagebox.showinfo("Mở rương", "Thiếu bộ ảnh nhận diện trong assets/chest.")
            return
        serial, package = self.serial.get().strip(), PACKAGE
        adb = self.adb
        session = self.sessions.device(adb, serial)
        control = session.control
        def emit(text):
            self.events.put(("device_progress", (session, text), None))

        def work():
            connect(adb,serial)
            if foreground_package(adb,serial) != package:
                raise AdbError("Hãy mở OMG 3Q và vào nhân vật trước.")
            device = AdbDevice(adb,serial,run_adb,input_text,package, capture_options={"dismiss_hints": False})
            skill = ChestSkill(device,stop=control.cancelled, clock=control.clock, sleeper=control.sleep,
                progress=emit)
            return skill.run()

        self._worker(work,self._chest_complete)

    def _chest_complete(self,result):
        self.last_chest_result = result
        self.status.set(result.message)
        if result.status in {"error", "blocked", "needs_samples", "partial"}:
            messagebox.showwarning("Mở rương đã dừng", result.message +
                (f"\nẢnh kiểm tra: {result.screenshot}" if result.screenshot else ""))

    def _worker(self, func, done=None):
        if not self.serial.get().strip():
            self.status.set("Hãy mở và chọn instance ở ô Thao tác trên trước.")
            return
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
                if kind == "excel_test_done":
                    self.batch_running = False
                    self.excel_test_button.configure(state='normal')
                    for button in self.script_buttons:
                        button.configure(state='normal')
                    completed = sum(r.get('completed', 0) for r in value)
                    errors = sum(bool(r.get('error')) for r in value)
                    self.status.set(f"Test kết thúc · {completed}/{getattr(self, '_test_expected', 6)} lượt · {errors} instance lỗi · Giữ nguyên X/V trong Excel.")
                    self._refresh_busy()
                elif kind == "batch_done":
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
                elif kind == "device_progress":
                    session, payload = value
                    session.status = payload
                    if session is self.sessions.device(self.adb, self.serial.get().strip()):
                        self.status.set(session.name + " · " + payload)
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


def main() -> None:
    root = tk.Tk()
    try:
        app = App(root)
        import sys
        if '--excel-login-test' in sys.argv:
            app._test_wait_forever = '--test-no-timeout' in sys.argv
            app._test_rounds = 1 if '--test-fourth-round' in sys.argv else 3
            app._test_iteration_offset = 3 if '--test-fourth-round' in sys.argv else 0
            if '--test-stt9-no-wait' in sys.argv:
                app._test_rounds = 1
                app._test_iteration_offset = 0
                app._test_options = dict(fixed_waits=False, instance_name='Android Device-1', target_stt=9, reuse_existing=True)
            if '--test-stt7-8-no-wait' in sys.argv:
                app._test_rounds = 2
                app._test_iteration_offset = 0
                app._test_options = dict(fixed_waits=False, instance_name='Android Device-1', allowed_stts=[7,8], reuse_existing=False)
            root.after(500, app.run_excel_login_test)
    except (AdbError, ValueError) as exc:
        messagebox.showerror("OMG 3Q", str(exc))
        root.destroy()
        return
    root.mainloop()


if __name__ == "__main__":
    main()
