"""Windows auto clicker with a desktop UI and an F6 start/stop hotkey."""

import ctypes
import os
import queue
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox, ttk

if os.name != "nt":
    raise SystemExit("This app requires Windows.")

user32 = ctypes.windll.user32
F6 = 0x75
MOUSE_FLAGS = {"Left": (0x0002, 0x0004), "Right": (0x0008, 0x0010)}

class Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

@dataclass(frozen=True)
class Settings:
    interval: float
    delay: float
    button: str
    position: tuple[int, int] | None
    limit: int | None

# Class controls auto clicker functionality.
class AutoClicker:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("Click Automation - Auto Clicker")
        root.geometry("500x670")
        root.resizable(False, False)
        root.configure(bg="#121826")
        self.stop_event: threading.Event | None = None
        self.run_id = 0
        self.events: queue.SimpleQueue[tuple[int, str]] = queue.SimpleQueue()
        self.f6_was_down = False
        self.countdown_ends = 0.0
        self.clicks = 0
        self.interval_ms = tk.StringVar(value="100")
        self.delay_s = tk.StringVar(value="3")
        self.mouse_button = tk.StringVar(value="Left")
        self.position_mode = tk.StringVar(value="Cursor")
        self.x = tk.StringVar(value="0")
        self.y = tk.StringVar(value="0")
        self.repeat_mode = tk.StringVar(value="Until stopped")
        self.repeat_count = tk.StringVar(value="100")
        self.status = tk.StringVar(value="Ready")
        self.click_display = tk.StringVar(value="0 clicks")

        self.make_style()
        self.build_ui()
        self.update_fields()
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.poll()

    def make_style(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Panel.TFrame", background="#1d2638")
        style.configure("Panel.TLabel", background="#1d2638", foreground="#e6ecf7", font=("Segoe UI", 10))
        style.configure("Title.TLabel", background="#121826", foreground="#f7f9ff", font=("Segoe UI Semibold", 20))
        style.configure("Sub.TLabel", background="#121826", foreground="#a9b7cc", font=("Segoe UI", 10))
        style.configure("TEntry", fieldbackground="#f7f9ff", padding=5)
        style.configure("TCombobox", fieldbackground="#f7f9ff", padding=4)

    def panel(self, parent: tk.Widget, title: str) -> ttk.Frame:
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=14)
        panel.pack(fill="x", pady=(0, 10))
        ttk.Label(panel, text=title, style="Panel.TLabel", font=("Segoe UI Semibold", 11)).pack(anchor="w", pady=(0, 9))
        return panel

    def build_ui(self) -> None:
        main = tk.Frame(self.root, bg="#121826", padx=22, pady=18)
        main.pack(fill="both", expand=True)
        ttk.Label(main, text="Click Automation - Auto Clicker", style="Title.TLabel").pack(anchor="w")
        ttk.Label(main, text="Choose settings, then press Start or F6.", style="Sub.TLabel").pack(anchor="w", pady=(2, 18))

        timing = ttk.Frame(self.panel(main, "Timing"), style="Panel.TFrame")
        timing.pack(fill="x")
        ttk.Label(timing, text="Interval (ms)", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(timing, textvariable=self.interval_ms, width=10).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(timing, text="Start delay (sec)", style="Panel.TLabel").grid(row=0, column=1, sticky="w", padx=(35, 0))
        ttk.Entry(timing, textvariable=self.delay_s, width=10).grid(row=1, column=1, sticky="w", padx=(35, 0), pady=(4, 0))

        click_panel = self.panel(main, "Click")
        click = ttk.Frame(click_panel, style="Panel.TFrame")
        click.pack(fill="x")
        ttk.Label(click, text="Mouse button", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Combobox(click, textvariable=self.mouse_button, values=("Left", "Right"), state="readonly", width=13).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(click, text="Position", style="Panel.TLabel").grid(row=0, column=1, sticky="w", padx=(28, 0))
        position = ttk.Combobox(click, textvariable=self.position_mode, values=("Cursor", "Fixed"), state="readonly", width=13)
        position.grid(row=1, column=1, sticky="w", padx=(28, 0), pady=(4, 0))
        position.bind("<<ComboboxSelected>>", lambda _event: self.update_fields())

        coords = ttk.Frame(click_panel, style="Panel.TFrame")
        coords.pack(fill="x", pady=(12, 0))
        ttk.Label(coords, text="X", style="Panel.TLabel").pack(side="left")
        self.x_entry = ttk.Entry(coords, textvariable=self.x, width=8)
        self.x_entry.pack(side="left", padx=(6, 15))
        ttk.Label(coords, text="Y", style="Panel.TLabel").pack(side="left")
        self.y_entry = ttk.Entry(coords, textvariable=self.y, width=8)
        self.y_entry.pack(side="left", padx=(6, 15))
        self.capture_button = ttk.Button(coords, text="Use cursor", command=self.capture_position)
        self.capture_button.pack(side="left")

        repeat = ttk.Frame(self.panel(main, "Repeat"), style="Panel.TFrame")
        repeat.pack(fill="x")
        mode = ttk.Combobox(repeat, textvariable=self.repeat_mode, values=("Until stopped", "Set number"), state="readonly", width=17)
        mode.pack(side="left")
        mode.bind("<<ComboboxSelected>>", lambda _event: self.update_fields())
        ttk.Label(repeat, text="Clicks", style="Panel.TLabel").pack(side="left", padx=(22, 8))
        self.count_entry = ttk.Entry(repeat, textvariable=self.repeat_count, width=10)
        self.count_entry.pack(side="left")

        self.start_button = tk.Button(
            main, text="Start  ·  F6", command=self.toggle, bg="#597df5", fg="white",
            activebackground="#7897ff", activeforeground="white", relief="flat",
            cursor="hand2", font=("Segoe UI Semibold", 12), height=2,
        )
        self.start_button.pack(fill="x", pady=(5, 12))
        status_row = tk.Frame(main, bg="#000835")
        status_row.pack(fill="x")
        tk.Label(status_row, textvariable=self.status, bg="#122474", fg="#a9b7cc", font=("Segoe UI", 10)).pack(side="left")
        tk.Label(status_row, textvariable=self.click_display, bg="#004CFF", fg="#a9b7cc", font=("Segoe UI", 10)).pack(side="right")
        ttk.Label(main, text="F6 works while this window is in the background.", style="Sub.TLabel").pack(anchor="w", pady=(13, 0))

    def update_fields(self) -> None:
        fixed = self.position_mode.get() == "Fixed"
        for widget in (self.x_entry, self.y_entry, self.capture_button):
            widget.configure(state="normal" if fixed else "disabled")
        self.count_entry.configure(state="normal" if self.repeat_mode.get() == "Set number" else "disabled")

    def capture_position(self) -> None:
        point = Point()
        if user32.GetCursorPos(ctypes.byref(point)):
            self.x.set(str(point.x))
            self.y.set(str(point.y))

    def read_settings(self) -> Settings | None:
        try:
            interval_ms = int(self.interval_ms.get())
            delay_s = float(self.delay_s.get())
            if interval_ms < 10 or not 0 <= delay_s <= 60:
                raise ValueError
            position = None
            if self.position_mode.get() == "Fixed":
                position = (int(self.x.get()), int(self.y.get()))
            limit = None
            if self.repeat_mode.get() == "Set number":
                limit = int(self.repeat_count.get())
                if limit < 1:
                    raise ValueError
            return Settings(interval_ms / 1000, delay_s, self.mouse_button.get(), position, limit)
        except ValueError:
            messagebox.showerror("Check settings", "Use an interval of at least 10 ms, a delay from 0 to 60 seconds, whole-number coordinates, and a positive click count.")
            return None

    def toggle(self) -> None:
        if self.stop_event is not None:
            self.stop_event.set()
            self.stop_event = None
            self.start_button.configure(text="Start  ·  F6", bg="#1e2e63")
            self.status.set("Stopped")
            return
        settings = self.read_settings()
        if settings is None:
            return
        self.run_id += 1
        self.clicks = 0
        self.click_display.set("0 clicks")
        self.stop_event = threading.Event()
        self.countdown_ends = time.monotonic() + settings.delay
        self.start_button.configure(text="Stop  ·  F6", bg="#161d72")
        self.status.set("Starting...")
        threading.Thread(target=self.click_loop, args=(self.run_id, self.stop_event, settings), daemon=True).start()

    # This function clicks the mouse.
    def click_loop(self, run_id: int, stop_event: threading.Event, settings: Settings) -> None:
        if stop_event.wait(settings.delay):
            return
        self.events.put((run_id, "running"))
        down, up = MOUSE_FLAGS[settings.button]
        clicks = 0
        while not stop_event.is_set():
            if settings.position is not None:
                user32.SetCursorPos(*settings.position)
            user32.mouse_event(down, 0, 0, 0, 0)
            user32.mouse_event(up, 0, 0, 0, 0)
            clicks += 1
            self.events.put((run_id, "click"))
            if settings.limit is not None and clicks >= settings.limit:
                self.events.put((run_id, "finished"))
                return
            if stop_event.wait(settings.interval):
                return
            
    # This function checks if F6 is presssed to start or stop.
    def poll(self) -> None:
        f6_down = bool(user32.GetAsyncKeyState(F6) & 0x8000)
        if f6_down and not self.f6_was_down:
            self.toggle()
        self.f6_was_down = f6_down
        while True:
            try:
                run_id, event = self.events.get_nowait()
            except queue.Empty:
                break
            if run_id != self.run_id:
                continue
            if event == "running" and self.stop_event is not None:
                self.status.set("Clicking")
            elif event == "click":
                self.clicks += 1
                self.click_display.set(f"{self.clicks:,} clicks")
            elif event == "finished" and self.stop_event is not None:
                self.stop_event = None
                self.start_button.configure(text="Start  ·  F6", bg="#597df5")
                self.status.set("Finished")
        if self.stop_event is not None and time.monotonic() < self.countdown_ends:
            self.status.set(f"Starting in {self.countdown_ends - time.monotonic():.1f}s — move the cursor")
        self.root.after(50, self.poll)

    def close(self) -> None:
        if self.stop_event is not None:
            self.stop_event.set()
        self.root.destroy()

if __name__ == "__main__":
    AutoClicker(tk.Tk()).root.mainloop()