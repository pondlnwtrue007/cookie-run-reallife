"""
Cookie Run Real-Life — เล่นด้วยการเคลื่อนไหวร่างกายจริง

loop หลัก: กล้อง -> MediaPipe Pose -> ตัดสิน JUMP/CROUCH -> ส่งปุ่มเข้าเกม
พร้อมหน้าต่าง debug โชว์กล้อง + โครงกระดูก + สถานะ + ค่าความไว

ปุ่มลัด (โฟกัสที่หน้าต่าง debug):
  C = calibrate ใหม่ (ยืนนิ่ง ~2 วิ)
  T = สลับโหมด DRY-RUN <-> ส่งปุ่มจริง
  [ / ] = ปรับความไว (ไวขึ้น / ไวน้อยลง)
  Q หรือ ESC = ออก
"""

import sys
import time
import cv2

# บังคับ console เป็น UTF-8 กัน UnicodeEncodeError ตอน print ภาษาไทย
# (เกิดได้เมื่อ locale เป็น cp874/cp1252 หรือถูก pipe)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import config as cfg
from camera import CameraStream
from pose_detector import PoseDetector
from motion_logic import MotionLogic, STATE_JUMP, STATE_CROUCH
from input_sender import InputSender

# สีสถานะ (BGR)
COLOR_STAND = (180, 180, 180)
COLOR_JUMP = (0, 220, 0)
COLOR_CROUCH = (0, 160, 255)
COLOR_INFO = (255, 255, 255)
COLOR_WARN = (0, 0, 255)


def open_camera():
    """เปิดกล้องแบบ threaded (MSMF+MJPG) แล้วรอเฟรมแรกก่อนคืนค่า"""
    cam = CameraStream(
        cfg.CAMERA_INDEX, cfg.CAMERA_WIDTH, cfg.CAMERA_HEIGHT,
        prefer_backend=cfg.CAMERA_BACKEND, use_mjpg=cfg.USE_MJPG, fps=cfg.CAMERA_FPS,
    )
    if not cam.is_opened():
        print(f"เปิดกล้อง index {cfg.CAMERA_INDEX} ไม่ได้")
        print("  - ปิดโปรแกรมอื่นที่ใช้กล้องอยู่ (Zoom/Teams/OBS/เบราว์เซอร์) แล้วลองใหม่")
        print("  - อย่าเปิด main.py ซ้อนหลายหน้าต่าง (กล้องเปิดได้ทีละโปรแกรม)")
        print("  - ถ้ามีหลายกล้อง ลองเปลี่ยน CAMERA_INDEX ใน config.py เป็น 1 หรือ 2")
        sys.exit(1)
    cam.start()
    # รอเฟรมแรกจาก thread (สูงสุด ~3 วิ)
    deadline = time.time() + 3.0
    while time.time() < deadline:
        ok, _ = cam.read()
        if ok:
            break
        time.sleep(0.02)
    print(f"เปิดกล้องด้วย backend {cam.backend_name} ที่ {cam.size[0]}x{cam.size[1]}")
    return cam


def draw_overlay(frame, logic: MotionLogic, sender: InputSender, fps):
    h, w = frame.shape[:2]

    # เส้น baseline + threshold (แปลง offset -> พิกัด y บนภาพ)
    if logic.is_ready:
        base_y_px = int(logic.baseline_y * h)
        span = logic.baseline_len * h  # 1.0 offset = 1 torso length เป็นพิกเซล
        jump_y = int(base_y_px - logic.jump_threshold * span)
        crouch_y = int(base_y_px + logic.crouch_threshold * span)
        cv2.line(frame, (0, jump_y), (w, jump_y), COLOR_JUMP, 2)
        cv2.line(frame, (0, base_y_px), (w, base_y_px), (200, 200, 200), 2)
        cv2.line(frame, (0, crouch_y), (w, crouch_y), COLOR_CROUCH, 2)
        cv2.putText(frame, "JUMP  [u/j]", (10, max(15, jump_y - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_JUMP, 1)
        cv2.putText(frame, "STAND [i/k]", (10, base_y_px - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220, 220, 220), 1)
        cv2.putText(frame, "CROUCH [o/l]", (10, min(h - 6, crouch_y + 16)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_CROUCH, 1)

    # ป้ายสถานะใหญ่
    if logic.state == STATE_JUMP:
        label, color = "JUMP", COLOR_JUMP
    elif logic.state == STATE_CROUCH:
        label, color = "CROUCH", COLOR_CROUCH
    else:
        label, color = "STAND", COLOR_STAND
    cv2.putText(frame, label, (w - 230, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 1.6, color, 3)

    # แถบข้อมูล
    mode = "DRY-RUN (no keys sent)" if sender.dry_run else "LIVE (sending keys)"
    mode_color = COLOR_WARN if not sender.dry_run else COLOR_INFO
    lines = [
        (f"MODE: {mode}", mode_color),
        (f"FPS: {fps:4.1f}", COLOR_INFO),
        (f"offset: {logic.last_offset:+.3f}", COLOR_INFO),
        (f"jump thr: {logic.jump_threshold:.2f}   crouch thr: {logic.crouch_threshold:.2f}", COLOR_INFO),
    ]
    y = 30
    for text, c in lines:
        cv2.putText(frame, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, c, 2)
        y += 26

    # สถานะ calibrate / คำแนะนำ
    if logic.is_calibrating:
        cv2.putText(frame, f"CALIBRATING... stand still {logic.calib_remaining():.1f}s",
                    (10, h - 58), cv2.FONT_HERSHEY_SIMPLEX, 0.7, COLOR_WARN, 2)
    elif not logic.is_ready:
        cv2.putText(frame, "Press C to calibrate (stand in view)",
                    (10, h - 58), cv2.FONT_HERSHEY_SIMPLEX, 0.7, COLOR_WARN, 2)

    cv2.putText(frame, "lines: u/j=JUMP  i/k=STAND  o/l=CROUCH   [ ]=both",
                (10, h - 32), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 255, 255), 1)
    cv2.putText(frame, "C=calibrate   T=toggle send   Q=quit",
                (10, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 255, 255), 1)
    return frame


def main():
    cap = open_camera()
    detector = PoseDetector()
    logic = MotionLogic(cfg)
    sender = InputSender(cfg)

    # เริ่ม calibrate อัตโนมัติทันทีที่เปิด
    logic.start_calibration()
    print("เริ่ม calibrate — ยืนนิ่งๆ ตรงหน้ากล้องสักครู่")

    prev_t = cv2.getTickCount()
    fps = 0.0

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("อ่านภาพจากกล้องไม่ได้")
                break

            if cfg.FLIP_HORIZONTAL:
                frame = cv2.flip(frame, 1)

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            pose = detector.process(rgb)

            event = logic.update(pose)
            if event == "jump":
                sender.jump()
            elif event == "crouch_start":
                sender.crouch_start()
            elif event == "crouch_end":
                sender.crouch_end()
            elif event == "fly_start":
                sender.fly_start()
            elif event == "fly_end":
                sender.fly_end()

            # คำนวณ FPS
            now = cv2.getTickCount()
            dt = (now - prev_t) / cv2.getTickFrequency()
            prev_t = now
            if dt > 0:
                fps = 0.9 * fps + 0.1 * (1.0 / dt) if fps > 0 else 1.0 / dt

            if cfg.SHOW_DEBUG_WINDOW:
                detector.draw(frame, pose)
                draw_overlay(frame, logic, sender, fps)
                cv2.imshow("Cookie Run Real-Life", frame)

                key = cv2.waitKey(1) & 0xFF
                if key in (ord(cfg.KEY_QUIT), 27):  # q หรือ ESC
                    break
                elif key == ord(cfg.KEY_CALIBRATE):
                    logic.start_calibration()
                    print("calibrate ใหม่ — ยืนนิ่งๆ")
                elif key == ord(cfg.KEY_TOGGLE_SEND):
                    dry = sender.toggle_dry_run()
                    print("โหมด:", "DRY-RUN" if dry else "LIVE ส่งปุ่มจริง")
                elif key == ord(cfg.KEY_SENS_DOWN):
                    logic.adjust_sensitivity(-cfg.SENS_STEP)
                elif key == ord(cfg.KEY_SENS_UP):
                    logic.adjust_sensitivity(cfg.SENS_STEP)
                # ปรับเส้นทีละเส้น (u/j = jump, i/k = stand, o/l = crouch)
                elif key == ord(cfg.KEY_JUMP_UP):
                    logic.move_jump_line(screen_up=True)
                elif key == ord(cfg.KEY_JUMP_DOWN):
                    logic.move_jump_line(screen_up=False)
                elif key == ord(cfg.KEY_STAND_UP):
                    logic.move_stand_line(screen_up=True)
                elif key == ord(cfg.KEY_STAND_DOWN):
                    logic.move_stand_line(screen_up=False)
                elif key == ord(cfg.KEY_CROUCH_UP):
                    logic.move_crouch_line(screen_up=True)
                elif key == ord(cfg.KEY_CROUCH_DOWN):
                    logic.move_crouch_line(screen_up=False)
    finally:
        sender.cleanup()
        detector.close()
        cap.release()
        cv2.destroyAllWindows()
        print("ปิดโปรแกรมเรียบร้อย")


if __name__ == "__main__":
    main()
