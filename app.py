"""
Cookie Run Real-Life — แอป GUI
เล่น Cookie Run ด้วยการกระโดด/ย่อจริง ผ่านกล้อง

รันด้วย:  py app.py
หรือใช้เป็น .exe (ดู build_exe.py)
"""

import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

import cv2
from PIL import Image, ImageTk

# บังคับ console เป็น UTF-8 (กันพังตอน print ภาษาไทย)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from paths import resource_path
from settings import Settings
from camera import CameraStream, list_cameras
from winfocus import target_focused, list_windows
from pose_detector import PoseDetector
from motion_logic import MotionLogic, STATE_JUMP, STATE_CROUCH, STATE_FLY
from input_sender import InputSender

# สี (ธีมมืด)
BG = "#1e1f26"
PANEL = "#2a2c36"
FG = "#e8e8ef"
MUTED = "#9a9ab0"
GREEN = "#3ad16a"
ORANGE = "#ff9f40"
GREY = "#c8c8d4"
RED = "#ff4d4d"
ACCENT = "#5b8cff"
CYAN = "#33d6e0"

# ฟอนต์ UI — Leelawadee UI มีตัวอักษรไทยในตัว (เรนเดอร์เหมือนกันทุกเครื่อง Win8+)
# เดิมใช้ Segoe UI ที่ไม่มีตัวไทย → Windows สลับฟอนต์ให้เอง ทำให้ไทยดูอ้วน/ต่างกันแต่ละเครื่อง
UIFONT = "Leelawadee UI"

# ปุ่มที่เลือกส่งเข้าเกมได้
KEY_CHOICES = ["space", "ctrl", "shift", "alt", "up", "down", "left", "right",
               "enter", "z", "x", "c", "a", "s", "d", "w", "q", "e", "f", "j", "k"]

# ตัวเลือกแรกใน dropdown หน้าต่าง = ส่งทุกหน้าต่าง (ปิดการกรอง)
SEND_ALL_LABEL = "(ทุกหน้าต่าง — ส่งตลอด)"


def draw_lines(frame, logic):
    """วาดเส้น JUMP / STAND / CROUCH ลงบนภาพ (BGR)"""
    if not logic.is_ready:
        return
    h, w = frame.shape[:2]
    base_px = int(logic.baseline_y * h)
    span = logic.baseline_len * h
    jump_y = int(base_px - logic.jump_threshold * span)
    crouch_y = int(base_px + logic.crouch_threshold * span)
    # BGR
    cv2.line(frame, (0, jump_y), (w, jump_y), (106, 209, 58), 2)
    cv2.line(frame, (0, base_px), (w, base_px), (200, 200, 200), 2)
    cv2.line(frame, (0, crouch_y), (w, crouch_y), (64, 159, 255), 2)
    cv2.putText(frame, "JUMP", (8, max(16, jump_y - 6)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (106, 209, 58), 2)
    cv2.putText(frame, "STAND", (8, base_px - 6),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 220), 2)
    cv2.putText(frame, "CROUCH", (8, min(h - 8, crouch_y + 18)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (64, 159, 255), 2)


class DetectionWorker:
    """เครื่องยนต์ตรวจจับ — ทำงานใน thread แยกไม่ให้ UI ค้าง"""

    def __init__(self, settings):
        self.s = settings
        self.cam = self.det = self.logic = self.sender = None
        self._thread = None
        self._running = False
        self._lock = threading.Lock()
        self._frame_rgb = None
        self.fps = 0.0
        self.state = "STAND"
        self.error = None
        self.backend_name = None
        self.cam_size = (0, 0)
        self.window_ok = True   # หน้าต่างเกม (MuMu) active อยู่ไหม (ตอนโหมดจริง)

    def start(self, index):
        self.stop()
        self.error = None
        self.s.CAMERA_INDEX = index
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    @property
    def running(self):
        return self._running

    def is_ready(self):
        return self.logic is not None and self._running

    def _run(self):
        try:
            self.cam = CameraStream(
                self.s.CAMERA_INDEX, self.s.CAMERA_WIDTH, self.s.CAMERA_HEIGHT,
                prefer_backend=self.s.CAMERA_BACKEND, use_mjpg=self.s.USE_MJPG,
                fps=self.s.CAMERA_FPS,
            )
            if not self.cam.is_opened():
                self.error = ("เปิดกล้องไม่ได้\nปิดโปรแกรมอื่นที่ใช้กล้อง "
                              "(Zoom/Teams/OBS/เบราว์เซอร์) หรือเลือกกล้องอื่น")
                self._running = False
                return
            self.cam.start()
            self.backend_name = self.cam.backend_name
            self.cam_size = self.cam.size

            self.det = PoseDetector()
            self.logic = MotionLogic(self.s)
            self.sender = InputSender(self.s)
            self.logic.start_calibration()

            prev = time.perf_counter()
            fps = 0.0
            while self._running:
                ok, frame = self.cam.read()
                if not ok:
                    time.sleep(0.005)
                    continue
                if self.s.FLIP_HORIZONTAL:
                    frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pose = self.det.process(rgb)

                event = self.logic.update(pose)
                # ส่งปุ่มเฉพาะตอนหน้าต่างเกม (MuMu) active — กันปุ่มรั่วไป OBS/เว็บ/แอปอื่น
                # (โหมดทดสอบไม่สนหน้าต่าง เพราะไม่ส่งปุ่มจริงอยู่แล้ว)
                focused = self.sender.dry_run or target_focused(self.s.TARGET_WINDOW)
                self.window_ok = focused
                # กระโดด (แตะครั้งเดียว)
                if event == "jump" and focused:
                    self.sender.jump()
                # สไลด์/บิน (กดค้าง) — sync ตามสถานะทุกเฟรม: ถ้าหลุดโฟกัสให้ปล่อยปุ่มค้าง
                if self.logic.crouching and focused:
                    self.sender.crouch_start()
                else:
                    self.sender.crouch_end()
                if self.logic.flying and focused:
                    self.sender.fly_start()
                else:
                    self.sender.fly_end()

                self.det.draw(frame, pose)
                draw_lines(frame, self.logic)
                annotated = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                now = time.perf_counter()
                dt = now - prev
                prev = now
                if dt > 0:
                    fps = 0.9 * fps + 0.1 / dt if fps > 0 else 1.0 / dt

                with self._lock:
                    self._frame_rgb = annotated
                    self.fps = fps
                    self.state = self.logic.state
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error = str(e)
        finally:
            if self.sender:
                self.sender.cleanup()
            if self.det:
                self.det.close()
            if self.cam:
                self.cam.release()
            self._running = False

    def get_frame(self):
        with self._lock:
            return self._frame_rgb

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.5)
        self._thread = None
        with self._lock:
            self._frame_rgb = None

    # --- ควบคุมจาก UI ---
    def calibrate(self):
        if self.logic:
            self.logic.start_calibration()

    def toggle_dry_run(self):
        if self.sender:
            return self.sender.toggle_dry_run()
        self.s.DRY_RUN = not self.s.DRY_RUN
        return self.s.DRY_RUN

    def dry_run(self):
        return self.sender.dry_run if self.sender else self.s.DRY_RUN

    def counts(self):
        if self.sender:
            return (self.sender.jump_count, self.sender.crouch_count,
                    self.sender.fly_count)
        return 0, 0, 0

    def move_line(self, which, up):
        if not self.logic:
            return
        if which == "jump":
            self.logic.move_jump_line(up)
        elif which == "stand":
            self.logic.move_stand_line(up)
        elif which == "crouch":
            self.logic.move_crouch_line(up)

    def sync_to_settings(self):
        """ดึงค่าเส้นล่าสุดกลับไปเก็บใน settings (ก่อนเซฟ)"""
        if self.logic:
            self.s.JUMP_THRESHOLD = self.logic.jump_threshold
            self.s.CROUCH_THRESHOLD = self.logic.crouch_threshold


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Cookie Run Real-Life 🍪")
        self.configure(bg=BG)
        self.resizable(False, False)
        try:
            self.iconbitmap(resource_path("app_icon.ico"))
        except Exception:
            pass

        self.s = Settings.load()
        self.s.DRY_RUN = True   # เปิดมาเป็นโหมดทดสอบเสมอ (กันส่งปุ่มมั่วตอนเพิ่งเปิด)
        self.worker = DetectionWorker(self.s)
        self.cameras = []            # list ของ (index, name)
        self._imgtk = None           # กัน GC ของภาพ

        self._build_ui()
        self.refresh_cameras()
        self.refresh_windows()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(30, self._tick)

    # ---------- UI ----------
    def _build_ui(self):
        f = (UIFONT, 11)
        fb = (UIFONT, 11, "bold")

        # แถบบน: เลือกกล้อง + Start/Stop
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=14, pady=(12, 6))
        tk.Label(top, text="กล้อง:", bg=BG, fg=FG, font=f).pack(side="left")
        self.cam_var = tk.StringVar()
        self.cam_combo = ttk.Combobox(top, textvariable=self.cam_var, state="readonly",
                                      width=32, font=f)
        self.cam_combo.pack(side="left", padx=6)
        tk.Button(top, text="↻", command=self.refresh_cameras, font=fb,
                  bg=PANEL, fg=FG, relief="flat", width=3).pack(side="left")
        self.start_btn = tk.Button(top, text="▶ เริ่ม", command=self.toggle_start,
                                   font=fb, bg=GREEN, fg="#10240f", relief="flat",
                                   width=10, padx=6, pady=4)
        self.start_btn.pack(side="right")

        # กลาง: วิดีโอซ้าย + คอนโทรลขวา
        mid = tk.Frame(self, bg=BG)
        mid.pack(fill="both", expand=True, padx=14, pady=6)

        self.video = tk.Label(mid, bg="#000000", width=640, height=480)
        self.video.grid(row=0, column=0, sticky="nw")
        self._show_placeholder()

        panel = tk.Frame(mid, bg=PANEL)
        panel.grid(row=0, column=1, sticky="nsew", padx=(12, 0))

        # แถบไกด์ "ทำอะไรต่อ" — เปลี่ยนตามสถานะ ช่วยมือใหม่
        self.guide_lbl = tk.Label(panel, text="① เลือกกล้อง แล้วกด ▶ เริ่ม (มุมขวาบน)",
                                  bg="#33354a", fg="#dfe4ff",
                                  font=(UIFONT, 10, "bold"),
                                  wraplength=280, justify="center", pady=8)
        self.guide_lbl.pack(fill="x", padx=14, pady=(12, 2))

        # สถานะใหญ่
        self.state_lbl = tk.Label(panel, text="—", bg=PANEL, fg=GREY,
                                  font=(UIFONT, 30, "bold"), width=9)
        self.state_lbl.pack(pady=(14, 0))
        self.fps_lbl = tk.Label(panel, text="", bg=PANEL, fg=MUTED, font=(UIFONT, 9))
        self.fps_lbl.pack()
        # ตัวนับ — เห็นชัดว่าตรวจจับ/ส่งปุ่มไปกี่ครั้ง (ทำงานจริงหรือเปล่า)
        self.count_lbl = tk.Label(panel, text="🦘 0   🛝 0   🕊️ 0", bg=PANEL,
                                  fg=FG, font=(UIFONT, 11))
        self.count_lbl.pack(pady=(4, 0))

        # ===== โหมด: ป้ายสถานะ (บอกว่าอยู่โหมดไหน) + ปุ่มสั่ง (บอกว่าคลิกแล้วเกิดอะไร) =====
        self.mode_status = tk.Label(panel, text="", font=(UIFONT, 11, "bold"), pady=6)
        self.mode_status.pack(fill="x", padx=14, pady=(14, 0))
        self.mode_btn = tk.Button(panel, text="", command=self.toggle_mode,
                                  font=(UIFONT, 13, "bold"), relief="flat",
                                  pady=12, cursor="hand2")
        self.mode_btn.pack(fill="x", padx=14, pady=(4, 6))
        self._update_mode_ui()

        # ปุ่ม calibrate
        self.calib_btn = tk.Button(panel, text="🧍 ตั้งท่ายืน (Calibrate)",
                                   command=self.do_calibrate, font=fb, relief="flat",
                                   bg=ACCENT, fg="#0a1533", padx=8, pady=6)
        self.calib_btn.pack(fill="x", padx=14, pady=6)
        self.calib_hint = tk.Label(panel, text="ยืนตรงหน้ากล้องแล้วกดปุ่มนี้",
                                   bg=PANEL, fg=MUTED, font=(UIFONT, 9))
        self.calib_hint.pack()

        # ปรับเส้น
        lines = tk.LabelFrame(panel, text=" ปรับเส้น ", bg=PANEL, fg=FG,
                              font=f, labelanchor="n", bd=1)
        lines.pack(fill="x", padx=14, pady=(12, 6))
        self.line_val = {}
        for key, name, color in [("jump", "JUMP (กระโดด)", GREEN),
                                 ("stand", "STAND (ยืน)", GREY),
                                 ("crouch", "CROUCH (สไลด์)", ORANGE)]:
            row = tk.Frame(lines, bg=PANEL)
            row.pack(fill="x", pady=3, padx=6)
            tk.Label(row, text=name, bg=PANEL, fg=color, font=f, width=15,
                     anchor="w").pack(side="left")
            tk.Button(row, text="▲", width=3, relief="flat", bg="#3a3d4a", fg=FG,
                      command=lambda k=key: self.move_line(k, True)).pack(side="left", padx=2)
            tk.Button(row, text="▼", width=3, relief="flat", bg="#3a3d4a", fg=FG,
                      command=lambda k=key: self.move_line(k, False)).pack(side="left")

        # ปรับโหมดบิน
        flyf = tk.LabelFrame(panel, text=" 🕊️ โหมดบิน (กางแขนกระพือ+เด้ง) ", bg=PANEL,
                             fg=CYAN, font=f, labelanchor="n", bd=1)
        flyf.pack(fill="x", padx=14, pady=6)
        for label, kind in [("ความไวกระพือ", "osc"), ("เวลาค้าง (วิ)", "delay")]:
            row = tk.Frame(flyf, bg=PANEL)
            row.pack(fill="x", pady=3, padx=6)
            tk.Label(row, text=label, bg=PANEL, fg=FG, font=f, width=15,
                     anchor="w").pack(side="left")
            tk.Button(row, text="▲", width=3, relief="flat", bg="#3a3d4a", fg=FG,
                      command=lambda k=kind: self.adjust_fly(k, +1)).pack(side="left", padx=2)
            tk.Button(row, text="▼", width=3, relief="flat", bg="#3a3d4a", fg=FG,
                      command=lambda k=kind: self.adjust_fly(k, -1)).pack(side="left")

        # ตั้งปุ่ม
        keys = tk.LabelFrame(panel, text=" ปุ่มที่ส่งเข้าเกม ", bg=PANEL, fg=FG,
                             font=f, labelanchor="n", bd=1)
        keys.pack(fill="x", padx=14, pady=6)
        kr1 = tk.Frame(keys, bg=PANEL); kr1.pack(fill="x", pady=3, padx=6)
        tk.Label(kr1, text="กระโดด =", bg=PANEL, fg=FG, font=f, width=10,
                 anchor="w").pack(side="left")
        self.jump_key_var = tk.StringVar(value=self.s.JUMP_KEY)
        jc = ttk.Combobox(kr1, textvariable=self.jump_key_var, values=KEY_CHOICES,
                          state="readonly", width=10, font=f)
        jc.pack(side="left"); jc.bind("<<ComboboxSelected>>", self.on_key_change)
        kr2 = tk.Frame(keys, bg=PANEL); kr2.pack(fill="x", pady=3, padx=6)
        tk.Label(kr2, text="สไลด์ =", bg=PANEL, fg=FG, font=f, width=10,
                 anchor="w").pack(side="left")
        self.crouch_key_var = tk.StringVar(value=self.s.CROUCH_KEY)
        cc = ttk.Combobox(kr2, textvariable=self.crouch_key_var, values=KEY_CHOICES,
                          state="readonly", width=10, font=f)
        cc.pack(side="left"); cc.bind("<<ComboboxSelected>>", self.on_key_change)

        # หน้าต่างเป้าหมาย — เลือกจาก dropdown (เหมือนเลือกกล้อง) กันปุ่มรั่ว
        twf = tk.LabelFrame(panel, text=" ส่งปุ่มเข้าหน้าต่าง (กันรั่ว) ", bg=PANEL, fg=FG,
                            font=f, labelanchor="n", bd=1)
        twf.pack(fill="x", padx=14, pady=6)
        tw = tk.Frame(twf, bg=PANEL)
        tw.pack(fill="x", pady=3, padx=6)
        self.target_combo = ttk.Combobox(tw, state="readonly", width=24, font=(UIFONT, 9))
        self.target_combo.pack(side="left")
        self.target_combo.bind("<<ComboboxSelected>>", self.on_target_select)
        tk.Button(tw, text="↻", command=self.refresh_windows, font=fb,
                  bg="#3a3d4a", fg=FG, relief="flat", width=3).pack(side="left", padx=4)

        # วิธีใช้
        tk.Button(panel, text="❓ วิธีใช้ / ตั้งค่าเส้น", command=self.show_help,
                  font=f, relief="flat", bg="#3a3d4a", fg=FG, pady=5).pack(
            fill="x", padx=14, pady=(12, 14))

        # แถบล่าง
        self.status = tk.Label(self, text="พร้อม", bg="#15161c", fg=MUTED,
                               anchor="w", font=(UIFONT, 9))
        self.status.pack(fill="x", side="bottom", ipady=3)

    def _show_placeholder(self):
        import numpy as np
        ph = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(ph, "Press  Start", (170, 250), cv2.FONT_HERSHEY_SIMPLEX,
                    1.2, (90, 90, 110), 2)
        self._set_image(ph)

    def _set_image(self, rgb):
        img = Image.fromarray(rgb)
        self._imgtk = ImageTk.PhotoImage(image=img)
        self.video.configure(image=self._imgtk, width=rgb.shape[1], height=rgb.shape[0])

    # ---------- กล้อง ----------
    def refresh_cameras(self):
        self.set_status("กำลังค้นหากล้อง...")
        self.update_idletasks()
        self.cameras = list_cameras()
        if not self.cameras:
            self.cam_combo["values"] = ["(ไม่พบกล้อง)"]
            self.cam_combo.current(0)
            self.set_status("ไม่พบกล้อง — เสียบกล้องแล้วกด ↻")
            return
        labels = [f"[{i}] {name}" for i, name in self.cameras]
        self.cam_combo["values"] = labels
        # เลือกตัวที่เคยใช้ถ้ามี
        sel = 0
        for k, (i, _n) in enumerate(self.cameras):
            if i == self.s.CAMERA_INDEX:
                sel = k
                break
        self.cam_combo.current(sel)
        self.set_status(f"พบกล้อง {len(self.cameras)} ตัว")

    def _selected_index(self):
        k = self.cam_combo.current()
        if 0 <= k < len(self.cameras):
            return self.cameras[k][0]
        return 0

    # ---------- ควบคุม ----------
    def toggle_start(self):
        if self.worker.running:
            self.worker.stop()
            self.start_btn.configure(text="▶ เริ่ม", bg=GREEN, fg="#10240f")
            self.cam_combo.configure(state="readonly")
            self._show_placeholder()
            self.set_status("หยุดแล้ว")
        else:
            if not self.cameras:
                messagebox.showwarning("ไม่พบกล้อง", "ไม่พบกล้อง กรุณาเสียบกล้องแล้วกด ↻")
                return
            idx = self._selected_index()
            self.worker.start(idx)
            self.start_btn.configure(text="■ หยุด", bg=RED, fg="#2a0d0d")
            self.cam_combo.configure(state="disabled")
            self.set_status("กำลังเปิดกล้อง...")

    def do_calibrate(self):
        if self.worker.is_ready():
            self.worker.calibrate()
        else:
            self.set_status("กด ▶ เริ่ม ก่อน ค่อย Calibrate")

    def toggle_mode(self):
        dry = self.worker.toggle_dry_run()
        self.s.DRY_RUN = dry
        self._update_mode_ui()
        if not dry:
            self.set_status("โหมดเล่นจริง — คลิกหน้าต่างเกม (MuMu) แล้วกระโดด/ย่อได้เลย")
        else:
            self.set_status("โหมดทดสอบ — ยังไม่ส่งปุ่มเข้าเกม")

    def _update_mode_ui(self):
        """อัปเดตป้ายสถานะ + ปุ่มโหมด ให้ชัดว่าตอนนี้อยู่โหมดไหน"""
        if self.worker.dry_run():
            self.mode_status.configure(
                text="🔴 ตอนนี้: โหมดทดสอบ  (ยังไม่ส่งปุ่มเข้าเกม)",
                bg="#4a3320", fg="#ffcf80")
            self.mode_btn.configure(text="▶  คลิกตรงนี้เพื่อเล่นจริง",
                                    bg=GREEN, fg="#0d2410")
        else:
            if self.worker.running and not self.worker.window_ok:
                # เล่นจริงแต่ยังไม่ได้อยู่หน้าต่าง MuMu -> ยังไม่ส่งปุ่ม (กันรั่ว)
                self.mode_status.configure(
                    text="🟡 เล่นจริง · รอสลับไปหน้าต่าง MuMu (ตอนนี้ยังไม่ส่งปุ่ม)",
                    bg="#4a4320", fg="#ffe08a")
            else:
                self.mode_status.configure(
                    text="🟢 ตอนนี้: เล่นจริง  (กำลังส่งปุ่มเข้าเกม)",
                    bg="#17361f", fg="#8effab")
            self.mode_btn.configure(text="⏸  คลิกเพื่อกลับไปโหมดทดสอบ",
                                    bg="#3a3d4a", fg=FG)

    def move_line(self, which, up):
        if self.worker.is_ready():
            self.worker.move_line(which, up)
        else:
            self.set_status("กด ▶ เริ่ม ก่อน ค่อยปรับเส้น")

    def adjust_fly(self, kind, direction):
        """ปรับค่าโหมดบินสดๆ (motion_logic อ่าน settings สดทุกเฟรม)"""
        if kind == "osc":
            # ▲ = ไวขึ้น (ขยับนิดเดียวก็บิน) = ลดค่า amplitude
            self.s.FLY_OSC_AMPLITUDE = round(
                max(0.03, self.s.FLY_OSC_AMPLITUDE - direction * 0.02), 3)
            self.set_status(f"ความไวกระพือ (osc): {self.s.FLY_OSC_AMPLITUDE} "
                            f"(น้อย=ไวขึ้น)")
        else:
            # ▲ = ค้างนานขึ้น (ร่วงช้าลง)
            self.s.FLY_RELEASE_DELAY = round(
                max(0.1, self.s.FLY_RELEASE_DELAY + direction * 0.1), 2)
            self.set_status(f"เวลาค้างก่อนร่วง: {self.s.FLY_RELEASE_DELAY} วิ")

    def on_key_change(self, _e=None):
        self.s.JUMP_KEY = self.jump_key_var.get()
        self.s.CROUCH_KEY = self.crouch_key_var.get()
        self.set_status(f"ปุ่ม: กระโดด={self.s.JUMP_KEY}  สไลด์={self.s.CROUCH_KEY}")

    def refresh_windows(self):
        """สแกนหน้าต่างที่เปิดอยู่ ใส่ใน dropdown (เลือกตัวที่ตรงกับค่าปัจจุบันไว้)"""
        self._windows = list_windows()
        values = [SEND_ALL_LABEL] + self._windows
        cur = (self.s.TARGET_WINDOW or "").strip()
        sel = 0
        if cur:
            match = next((i for i, t in enumerate(self._windows)
                          if cur.lower() == t.lower()), None)
            if match is not None:
                sel = match + 1
            else:
                # ค่าปัจจุบัน (เช่น "MuMu") ไม่ตรงชื่อเต็มไหนเป๊ะ — โชว์ค่านี้ไว้ให้เห็นชัด
                values.insert(1, cur)
                sel = 1
        self.target_combo["values"] = values
        self.target_combo.current(sel)

    def on_target_select(self, _e=None):
        v = self.target_combo.get()
        self.s.TARGET_WINDOW = "" if v == SEND_ALL_LABEL else v
        self.set_status("ส่งปุ่มเข้าหน้าต่าง: " + (v if self.s.TARGET_WINDOW else "ทุกหน้าต่าง"))

    def set_status(self, text):
        self.status.configure(text="  " + text)

    # ---------- loop อัปเดต UI ----------
    def _tick(self):
        w = self.worker
        if w.error:
            err = w.error
            w.error = None
            messagebox.showerror("ผิดพลาด", err)
            # reset เป็นสถานะ "หยุด" (ไม่ใช่รีสตาร์ท) กันวนลูป error
            w.stop()
            self.start_btn.configure(text="▶ เริ่ม", bg=GREEN, fg="#10240f")
            self.cam_combo.configure(state="readonly")
            self._show_placeholder()
            self.set_status("หยุดแล้ว (มีข้อผิดพลาด)")
        frame = w.get_frame()
        if frame is not None:
            self._set_image(frame)

        # แถบไกด์: บอกขั้นตอนถัดไปตามสถานะ
        if not w.running:
            guide = "① เลือกกล้อง แล้วกด ▶ เริ่ม (มุมขวาบน)"
        elif not w.is_ready():
            guide = "กำลังเปิดกล้อง... รอสักครู่"
        elif w.logic.is_calibrating:
            guide = "ยืนนิ่งๆ กำลังจำท่ายืน..."
        elif not w.logic.is_ready:
            guide = "② ยืนตรงหน้ากล้อง แล้วกด 🧍 ตั้งท่ายืน"
        elif w.dry_run():
            guide = "③ กดปุ่มเขียว 'เล่นจริง' ด้านล่าง → คลิกหน้าต่างเกม → กระโดด/ย่อ"
        else:
            guide = "✅ พร้อมเล่น! คลิกหน้าต่างเกม (MuMu) แล้วกระโดด/ย่อหน้ากล้อง"
        self.guide_lbl.configure(text=guide)

        # สถานะ
        if w.is_ready():
            st = w.state
            if st == STATE_FLY:
                self.state_lbl.configure(text="FLY", fg=CYAN)
            elif st == STATE_JUMP:
                self.state_lbl.configure(text="JUMP", fg=GREEN)
            elif st == STATE_CROUCH:
                self.state_lbl.configure(text="CROUCH", fg=ORANGE)
            else:
                self.state_lbl.configure(text="STAND", fg=GREY)

            if w.logic.is_calibrating:
                self.calib_hint.configure(
                    text=f"กำลังตั้งท่า... ยืนนิ่ง {w.logic.calib_remaining():.1f}s", fg=ORANGE)
            elif not w.logic.is_ready:
                self.calib_hint.configure(text="กด 'ตั้งท่ายืน' แล้วยืนนิ่ง", fg=ORANGE)
            else:
                self.calib_hint.configure(
                    text=f"jump {w.logic.jump_threshold:.2f} · crouch {w.logic.crouch_threshold:.2f}",
                    fg=MUTED)

            self.fps_lbl.configure(text=f"{w.fps:.0f} FPS · {w.backend_name} {w.cam_size[0]}x{w.cam_size[1]}")

            # ตัวนับ jump/crouch/fly (สีเขียวถ้าส่งจริง เทาถ้าโหมดทดสอบ)
            jc, cc, fc = w.counts()
            self.count_lbl.configure(text=f"🦘 {jc}   🛝 {cc}   🕊️ {fc}",
                                     fg=(GREEN if not w.dry_run() else MUTED))
        else:
            self.state_lbl.configure(text="—", fg=GREY)

        # อัปเดตป้าย/ปุ่มโหมดเสมอ (ให้ตรงกับสถานะจริงตลอด)
        self._update_mode_ui()
        self.after(30, self._tick)

    # ---------- วิธีใช้ ----------
    def show_help(self):
        win = tk.Toplevel(self)
        win.title("วิธีใช้ / ตั้งค่าเส้น")
        win.configure(bg=BG)
        win.geometry("560x620")
        txt = tk.Text(win, bg=PANEL, fg=FG, font=(UIFONT, 11), wrap="word",
                      relief="flat", padx=16, pady=14)
        txt.pack(fill="both", expand=True, padx=10, pady=10)
        txt.insert("end", HELP_TEXT)
        txt.configure(state="disabled")
        tk.Button(win, text="ปิด", command=win.destroy, font=(UIFONT, 11),
                  bg=ACCENT, fg="#0a1533", relief="flat", pady=6).pack(pady=(0, 10))

    def on_close(self):
        self.worker.sync_to_settings()
        self.s.JUMP_KEY = self.jump_key_var.get()
        self.s.CROUCH_KEY = self.crouch_key_var.get()
        # TARGET_WINDOW ถูกตั้งแล้วตอนเลือกใน dropdown
        self.worker.stop()
        self.s.save()
        self.destroy()


HELP_TEXT = """🍪 วิธีเล่น Cookie Run ด้วยตัวจริง

1) เลือกกล้อง แล้วกด ▶ เริ่ม
2) ยืนตรงหน้ากล้อง (ให้เห็นตั้งแต่หัวถึงเอว) แล้วกด "ตั้งท่ายืน (Calibrate)"
   ยืนนิ่งๆ 2 วินาที ระบบจะจำท่ายืนของคุณ

━━━━━━━━━━━━━━━━━━━━━━━━
เส้น 3 เส้นบนภาพคืออะไร?

🟢 JUMP (เขียว) — ถ้าหัว/ตัวขึ้นเลยเส้นนี้ = กระโดดในเกม
⬜ STAND (เทา)  — ระดับตัวตอนยืนปกติ (ได้จากการ Calibrate)
🟠 CROUCH (ส้ม) — ถ้าย่อตัวต่ำกว่าเส้นนี้ = สไลด์ในเกม

ปรับเส้นด้วยปุ่ม ▲ ▼ ทางขวา:
• เส้น JUMP เข้าใกล้ STAND → กระโดดเบาๆ ก็ติด (ไวขึ้น)
• เส้น JUMP ห่าง STAND → ต้องกระโดดสูงขึ้น (ไวน้อยลง)
• เส้น CROUCH เข้าใกล้ STAND → ย่อนิดเดียวก็สไลด์
• ถ้าเส้น STAND ไม่ตรงระดับตัว ให้ Calibrate ใหม่

━━━━━━━━━━━━━━━━━━━━━━━━
🕊️ ท่าบิน (ตอน Bonus Time)

กางแขนสองข้าง (ท่า T) กระพือปีกขึ้น-ลง + เด้งตัวไปด้วยเรื่อยๆ
 = กดกระโดดค้าง = บินขึ้น
หยุดขยับ = ปล่อย = ร่วงลง  (ต้องขยับต่อเนื่องถึงจะบินอยู่)

ปรับที่กล่อง "โหมดบิน":
• ความไวกระพือ — ▲ ขยับนิดเดียวก็บิน / ▼ ต้องขยับแรงขึ้น
• เวลาค้าง — หยุดขยับกี่วิถึงร่วง (▲ ร่วงช้า / ▼ ร่วงไว)

━━━━━━━━━━━━━━━━━━━━━━━━
ตั้งค่าใน MuMuPlayer (ทำครั้งเดียว)

เปิดเมนู keymapping ในเกม แล้วผูกปุ่มให้ตรงกับที่ตั้งในแอป:
• ปุ่ม "กระโดด" (ค่าเริ่มต้น = space) → วางจุดแตะกระโดด
• ปุ่ม "สไลด์" (ค่าเริ่มต้น = ctrl) → วางจุด/ปัดสไลด์ (เปิดกดค้างถ้ามี)

━━━━━━━━━━━━━━━━━━━━━━━━
เริ่มเล่นจริง

1) กดปุ่ม "โหมด" ให้เป็น "เล่นจริง ✅"
2) คลิกที่หน้าต่างเกม (MuMu) ให้ทำงานอยู่ด้านหน้า
3) กระโดด/ย่อจริงได้เลย!

⚠️ ต้องเปิดแบบ Administrator (เปิดผ่าน "เล่น Cookie Run.bat"
   หรือตัว .exe จะขอสิทธิ์ให้เอง) ไม่งั้นปุ่มไม่เข้า MuMu
⚠️ ปุ่มจะเข้าเกมเฉพาะตอนหน้าต่างเกมถูกเลือกอยู่
💡 ลองโหมด "ทดสอบ" ก่อน เพื่อดูว่า JUMP/CROUCH จับถูกจังหวะ
"""


def selftest():
    """ทดสอบแบบ headless: สร้าง AI + เปิดกล้อง + ประมวลผล ใช้ยืนยันว่า .exe ครบ"""
    print("=== SELFTEST ===", flush=True)
    from settings import Settings
    s = Settings()
    w = DetectionWorker(s)
    w.start(0)
    ok = False
    for _ in range(60):  # รอสูงสุด ~6 วิ
        if w.get_frame() is not None:
            ok = True
            break
        if w.error:
            break
        time.sleep(0.1)
    print(f"ready={w.is_ready()} frame={w.get_frame() is not None} "
          f"backend={w.backend_name} err={w.error}", flush=True)
    w.stop()
    print("SELFTEST", "PASS" if ok else "FAIL", flush=True)
    sys.exit(0 if ok else 1)


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
