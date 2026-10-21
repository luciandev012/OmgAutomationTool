"""Checkbox commands address independent persistent sessions by instance name."""
import queue
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import threading
import tkinter as tk
from tkinter import ttk
from emulator_instances import LaunchCancelled, open_instance
from task_sessions import active_session


class InstanceDialog:
    log = logging.getLogger('omg.instance_launch')

    def __init__(self, app, provider):
        self.log = logging.getLogger('omg.instance_launch')
        if not self.log.handlers:
            try:
                log_path = Path(__file__).with_name('runtime') / 'instance-launch.log'
                log_path.parent.mkdir(exist_ok=True)
                handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=2, encoding='utf-8')
                handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
                self.log.addHandler(handler)
                self.log.setLevel(logging.INFO)
                self.log.propagate = False
            except OSError:
                pass
        self.app, self.provider = app, provider
        self.events = queue.Queue()
        self.scanning = False
        self.instances, self.checks, self.state_labels = [], [], {}
        self.window = tk.Toplevel(app.root)
        self.window.title(f"{provider.label} · Điều khiển instance")
        self.window.geometry('820x470')
        self.window.transient(app.root)
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        body = ttk.Frame(self.window, padding=12)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='Tích chọn máy → chọn hành động · Dấu tích tự xóa sau mỗi lệnh').pack(anchor='w')
        selection = ttk.Frame(body)
        selection.pack(fill='x', pady=(8,0))
        ttk.Button(selection, text='Chọn tất cả', command=lambda: self.set_checks(True)).pack(side='left')
        ttk.Button(selection, text='Bỏ chọn tất cả', command=lambda: self.set_checks(False)).pack(side='left', padx=6)
        self.selection_count = tk.StringVar(value='Đã chọn 0 instance')
        ttk.Label(selection, textvariable=self.selection_count).pack(side='right')
        listing = ttk.Frame(body)
        listing.pack(fill='both', expand=True, pady=8)
        self.canvas = tk.Canvas(listing, height=220, highlightthickness=0)
        scrollbar = ttk.Scrollbar(listing, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.rows = ttk.Frame(self.canvas)
        embedded = self.canvas.create_window((0,0), window=self.rows, anchor='nw')
        self.rows.bind('<Configure>', lambda event: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda event: self.canvas.itemconfigure(embedded, width=event.width))
        self.message = tk.StringVar(value='Đang quét instance…')
        ttk.Label(body, textvariable=self.message, wraplength=780).pack(anchor='w')
        ttk.Label(body, text='Tạm dừng / Dừng tác vụ ngưng thao tác của tool; giả lập và game vẫn mở.', wraplength=780).pack(anchor='w', pady=4)
        actions = ttk.Frame(body)
        actions.pack(fill='x', pady=(8,0))
        self.refresh = ttk.Button(actions, text='Làm mới', command=self.scan)
        self.refresh.pack(side='left')
        self.start = ttk.Button(actions, text='Khởi động', command=self.run)
        self.start.pack(side='left', padx=6)
        self.pause = ttk.Button(actions, text='Tạm dừng', command=lambda: self.control_selected('pause'))
        self.pause.pack(side='left')
        self.resume = ttk.Button(actions, text='Tiếp tục', command=lambda: self.control_selected('resume'))
        self.resume.pack(side='left', padx=6)
        self.stop = ttk.Button(actions, text='Dừng tác vụ', command=lambda: self.control_selected('stop'))
        self.stop.pack(side='left')
        ttk.Button(actions, text='Đóng', command=self.close).pack(side='right')
        self.scan()
        self.window.after(100, self.poll)

    def selected(self):
        return [instance for instance, checked in zip(self.instances, self.checks) if checked.get()]

    def take_selection(self):
        # Snapshot before clearing; running workers never read mutable checkboxes.
        selected = tuple(self.selected())
        for checked in self.checks:
            checked.set(False)
        self.update_count()
        return selected

    def update_count(self):
        count = len(self.selected())
        self.selection_count.set(f'Đã chọn {count}/{len(self.instances)} instance')
        for button in (self.start, self.pause, self.resume, self.stop):
            button.configure(state='normal' if count and not self.scanning else 'disabled')

    def set_checks(self, value):
        if self.scanning:
            return
        for checked in self.checks:
            checked.set(value)
        self.update_count()

    def scan(self):
        if self.scanning:
            return
        self.take_selection()
        self.scanning = True
        self.update_count()
        self.refresh.configure(state='disabled')
        self.message.set('Đang nạp danh sách instance…')
        def work():
            try:
                self.events.put(('list', self.provider.instances()))
            except Exception as exc:
                self.events.put(('error', str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def run(self):
        if self.scanning:
            return
        selected = self.take_selection()
        if not selected:
            self.message.set('Hãy tích chọn ít nhất một instance.')
            return
        package = self.app.package.get().strip()
        started, skipped = [], []
        for instance in selected:
            session = self.app.sessions.instance(self.provider, instance)
            if not session.begin():
                skipped.append(instance.name)
                continue
            started.append(instance.name)
            def work(instance=instance, session=session):
                def progress(text):
                    session.status = text
                    self.log.info('%s', text)
                try:
                    with active_session(session):
                        connection = open_instance(self.provider, instance, package,
                            self.app_adb, self.app_launch, session.control, progress,
                            on_device=lambda adb, serial: self.app.sessions.bind(session, adb, serial))
                    session.finish('Đã mở OMG 3Q')
                    self.log.info('%s: game đã mở', instance.name)
                    self.app.events.put(('instance_ready', session, None))
                except LaunchCancelled:
                    session.finish('Đã dừng tác vụ')
                    self.log.info('%s: đã dừng tác vụ', instance.name)
                except Exception as exc:
                    session.finish(f'Lỗi: {exc}')
                    self.log.error('%s: %s', instance.name, exc)
                finally:
                    self.app.events.put(('session_changed', None, None))
            try:
                threading.Thread(target=work, daemon=True).start()
            except Exception as exc:
                session.finish(f'Lỗi: {exc}')
        message = f'Đã gửi lệnh khởi động song song {len(started)} instance.'
        if skipped:
            message += ' Đang có tác vụ, giữ nguyên: ' + ', '.join(skipped) + '.'
        self.message.set(message)
        self.app._refresh_busy()

    def control_selected(self, action):
        if self.scanning:
            return
        selected = self.take_selection()
        if not selected:
            self.message.set('Hãy tích chọn instance cần điều khiển.')
            return
        for instance in selected:
            control = self.app.sessions.instance(self.provider, instance).control
            if action == 'pause':
                control.paused.set()
            elif action == 'resume':
                control.paused.clear()
            else:
                control.cancelled.set()
        label = {'pause': 'Tạm dừng sau lệnh hiện tại', 'resume': 'Tiếp tục', 'stop': 'Dừng tác vụ sau lệnh hiện tại'}[action]
        self.message.set(label + ': ' + ', '.join(instance.name for instance in selected))
        self.app._refresh_busy()

    @staticmethod
    def app_adb(*args, **kwargs):
        from omg3q_tool import run_adb
        return run_adb(*args, **kwargs)

    @staticmethod
    def app_launch(*args, **kwargs):
        from omg3q_tool import launch_game
        return launch_game(*args, **kwargs)

    def close(self):
        # Workers and controls belong to the app, not this temporary window.
        self.window.destroy()
        self.app.instance_dialog = None
        self.app.provider_combo.configure(state='readonly')

    def poll(self):
        if not self.window.winfo_exists():
            return
        try:
            while True:
                kind, value = self.events.get_nowait()
                self.scanning = False
                self.refresh.configure(state='normal')
                if kind == 'list':
                    self.instances = value
                    for widget in self.rows.winfo_children():
                        widget.destroy()
                    self.checks, self.state_labels = [], {}
                    for instance in value:
                        row = ttk.Frame(self.rows, padding=(4,5))
                        row.pack(fill='x')
                        checked = tk.BooleanVar(value=False)
                        ttk.Checkbutton(row, text=instance.name, variable=checked,
                            command=self.update_count).pack(side='left')
                        session = self.app.sessions.instance(self.provider, instance)
                        if session.status == 'Sẵn sàng':
                            session.status = 'Đang chạy' if instance.running else 'Đã tắt'
                        label = ttk.Label(row, text=session.state(), wraplength=480)
                        label.pack(side='right', padx=10)
                        self.state_labels[instance.index] = label
                        self.checks.append(checked)
                    self.message.set(f'Tìm thấy {len(value)} instance. Chọn máy rồi chọn hành động.')
                else:
                    self.message.set(value)
                self.update_count()
        except queue.Empty:
            pass
        for instance in self.instances:
            self.state_labels[instance.index].configure(text=self.app.sessions.instance(self.provider, instance).state())
        self.window.after(150, self.poll)
