# -*- coding: utf-8 -*-
"""自动化引擎:逐个号码搜索 → 判定三种情形 → 打标签/发好友请求 → 写回结果。

设计成可被 GUI 在后台线程里驱动:
  - on_log(str)         输出一行日志
  - on_progress(dict)   汇报进度/统计
  - stop_event          threading.Event,置位即尽快安全停止
号码文件为 txt,处理完一个立即写回(断点续跑;重跑自动跳过已标记行)。
"""

import os
import re
import json
import time
import random
import datetime

import pyautogui
import pyperclip
import win32gui
import win32con

from matcher import TemplateMatcher, grab_screen, detect_system_scale

pyautogui.FAILSAFE = True   # 鼠标甩到左上角 = 紧急停止
pyautogui.PAUSE = 0.05

DIALOG_CLASS = "SearchExternalsWnd"   # 「添加客户」搜索弹窗类名

# 结果标记
R_FRIEND = "已是好友"
R_SENT = "已发送好友请求"
R_INVALID = "手机号码无微信信息"

# 默认模板(150% 屏)下,验证语输入框相对「发送」按钮的偏移,按匹配缩放缩放
INVITE_INPUT_OFFSET = (0, -112)


class StopRequested(Exception):
    pass


class DialogGone(Exception):
    pass


class Engine:
    def __init__(self, cfg, templates_dir, on_log=None, on_progress=None, stop_event=None):
        self.cfg = cfg
        self.on_log = on_log or (lambda s: None)
        self.on_progress = on_progress or (lambda d: None)
        self.stop_event = stop_event

        base_scale = cfg.get("dpi_scale", 0) or 0
        if base_scale <= 0:
            if cfg.get("template_set") == "custom":
                base_scale = 1.0   # 自定义模板与屏幕同源
            else:
                # 默认模板截于 150% 屏;用户屏缩放 / 150% = 相对缩放
                sysscale = detect_system_scale()
                base_scale = max(0.3, sysscale / 1.5)
        self.matcher = TemplateMatcher(templates_dir, cfg.get("threshold", 0.82), base_scale)
        self.geometry = self._load_geometry(templates_dir)

        self.delay = (float(cfg.get("delay_min", 8)), float(cfg.get("delay_max", 15)))
        self.cap = int(cfg.get("daily_cap", 100))
        self.enable_tag = bool(cfg.get("enable_tag", False))
        self.tag_name = (cfg.get("tag_name") or "").strip()
        self.remark = cfg.get("remark", "")
        self.debug_dir = os.path.join(os.path.dirname(os.path.dirname(templates_dir)), "debug") \
            if "templates" in templates_dir else "debug"

    # ================= 基础设施 =================

    def _load_geometry(self, tdir):
        p = os.path.join(tdir, "geometry.json")
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def log(self, msg):
        stamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.on_log("[{}] {}".format(stamp, msg))

    def _check_stop(self):
        if self.stop_event is not None and self.stop_event.is_set():
            raise StopRequested()

    def find(self, name, screen=None, region=None, threshold=None):
        return self.matcher.find(name, screen=screen, region=region, threshold=threshold)

    def wait_any(self, names_regions, timeout, poll=0.5):
        end = time.time() + timeout
        while time.time() < end:
            self._check_stop()
            screen = grab_screen()
            for name, region in names_regions:
                if not self.matcher.has(name):
                    continue
                hit = self.find(name, screen=screen, region=region)
                if hit:
                    return name, hit
            time.sleep(poll)
        return None, None

    def wait_gone(self, name, region, timeout):
        end = time.time() + timeout
        misses = 0
        while time.time() < end:
            self._check_stop()
            if self.find(name, region=region) is None:
                misses += 1
                if misses >= 2:
                    return True
            else:
                misses = 0
            time.sleep(0.4)
        return False

    def click(self, x, y, jitter=2):
        self._check_stop()
        x += random.randint(-jitter, jitter)
        y += random.randint(-jitter, jitter)
        pyautogui.moveTo(x, y, duration=random.uniform(0.15, 0.32))
        pyautogui.click()
        time.sleep(random.uniform(0.4, 0.85))

    def paste(self, text):
        pyperclip.copy(text)
        time.sleep(0.15)
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.12)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(random.uniform(0.3, 0.55))

    def save_debug(self, tag):
        try:
            os.makedirs(self.debug_dir, exist_ok=True)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            from PIL import ImageGrab
            ImageGrab.grab().save(os.path.join(self.debug_dir, "{}_{}.png".format(tag, ts)))
        except Exception:
            pass

    # ================= 窗口 =================

    def dialog_rect(self):
        hwnd = win32gui.FindWindow(DIALOG_CLASS, None)
        if not hwnd or not win32gui.IsWindowVisible(hwnd):
            return None, None
        return hwnd, win32gui.GetWindowRect(hwnd)

    def focus_dialog(self, hwnd):
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.25)
        except Exception:
            pass

    # ================= 号码文件 =================

    @staticmethod
    def load_numbers(path):
        with open(path, "rb") as f:
            raw = f.read()
        enc = None
        for cand in ("utf-8-sig", "utf-8", "gbk"):
            try:
                text = raw.decode(cand)
                enc = cand
                break
            except UnicodeDecodeError:
                continue
        if enc is None:
            raise RuntimeError("无法识别 txt 编码")
        entries = []
        for line in text.splitlines():
            m = re.match(r"^\s*(1\d{10})(?:[\s,\t]+(.*\S))?\s*$", line)
            if m:
                entries.append({"raw": line, "num": m.group(1), "remark": m.group(2) or None})
            else:
                entries.append({"raw": line, "num": None, "remark": None})
        return entries, enc

    @staticmethod
    def write_numbers(path, entries, enc):
        lines = []
        for e in entries:
            if e["num"] and e["remark"]:
                lines.append("{}\t{}".format(e["num"], e["remark"]))
            else:
                lines.append(e["raw"])
        tmp = path + ".tmp"
        with open(tmp, "w", encoding=enc, newline="") as f:
            f.write("\r\n".join(lines) + "\r\n")
        os.replace(tmp, path)

    def apply_result(self, entries, num, remark, path, enc):
        for e in entries:
            if e["num"] == num and not e["remark"]:
                e["remark"] = remark
        self.write_numbers(path, entries, enc)

    # ================= 标签 =================

    def _do_tagging(self, number, add_btn):
        """在非好友卡片上打标签。成功返回 True。"""
        screen = grab_screen()
        tag_search = (add_btn["x"] - 480, add_btn["y"] - 440, add_btn["x"] + 480, add_btn["y"])
        anchor = self.find("open_tag_row", screen=screen, region=tag_search)
        if anchor is None:
            self.save_debug("no_tagrow_{}".format(number))
            return False

        # 点标签行(点文字本体最稳,失败再往右试)
        opened = False
        for dx in (0, 130, 300):
            self.click(anchor["x"] + dx, anchor["y"], jitter=1)
            name, _ = self.wait_any([("panel_search", None)], 3)
            if name:
                opened = True
                break
        if not opened:
            self.save_debug("no_tagpanel_{}".format(number))
            return False
        time.sleep(0.5)

        ps = self.find("panel_search")
        if ps is None:
            self.save_debug("no_panelsearch_{}".format(number))
            return False

        # 选中目标标签,三级策略,由稳到兜:
        #  1) 目标标签此刻就在面板里可见 -> 直接模板命中并点击(最稳,校准用户即此路径)
        #  2) 不可见 -> 在面板搜索框输入标签名过滤,过滤后再试一次模板命中
        #  3) 仍找不到 -> 用『搜索框 + 几何偏移』推算第一个标签位置点击
        chip = self.find("panel_first_chip")
        if chip is None and self.tag_name:
            self.click(ps["x"], ps["y"])
            self.paste(self.tag_name)
            time.sleep(1.0)
            chip = self.find("panel_first_chip")
            ps = self.find("panel_search") or ps
        if chip is not None:
            self.click(chip["x"], chip["y"])
        else:
            off = self._chip_offset()
            chip_x = int(ps["x"] + off[0] * ps.get("scale", 1.0))
            chip_y = int(ps["y"] + off[1] * ps.get("scale", 1.0))
            self.click(chip_x, chip_y)
        time.sleep(0.3)

        conf = self.find("panel_confirm")
        if conf is None:
            self.save_debug("no_panelconfirm_{}".format(number))
            return False
        self.click(conf["x"], conf["y"])
        self.wait_gone("panel_search", None, 4)
        return True

    def _chip_offset(self):
        """第一个标签相对面板搜索框的偏移(模板原生像素)。"""
        g = self.geometry
        if "panel_search" in g and "panel_first_chip" in g:
            sx, sy = g["panel_search"]
            cx, cy = g["panel_first_chip"]
            return (cx - sx, cy - sy)
        # 兜底:搜索框下方一点
        return (0, 60)

    # ================= 单个号码 =================

    def process_one(self, number):
        hwnd, drect = self.dialog_rect()
        if hwnd is None:
            raise DialogGone()
        self.focus_dialog(hwnd)
        dl, dt, dr, db = drect
        dialog_region = (dl - 10, dt - 10, dr + 10, db + 10)

        # 1) 搜索框
        icon = self.find("search_box", region=dialog_region)
        if icon is None:
            self.click(dl + 80, dt + 45)
            icon = self.find("search_box", region=dialog_region)
            if icon is None:
                self.save_debug("no_searchbox_{}".format(number))
                return None
        self.click(icon["x"], icon["y"])
        self.click(icon["x"], icon["y"])

        # 2) 输入号码回车
        self.paste(number)
        pyautogui.press("enter")

        # 3) 等错误弹窗或结果行
        name, hit = self.wait_any(
            [("error_confirm", dialog_region), ("result_row", dialog_region)],
            self.cfg.get("wait_result_timeout", 12))
        if name is None:
            self.save_debug("no_result_{}".format(number))
            return None

        # 情形3:无效号码
        if name == "error_confirm":
            self.click(hit["x"], hit["y"])
            return R_INVALID

        # 有结果:先看结果行是否「已添加」
        row_band = (dl, hit["y"] - 32, dr, hit["y"] + 32)
        if self.matcher.has("added_flag") and self.find("added_flag", region=row_band):
            return R_FRIEND

        # 打开卡片
        self.click(hit["x"] + 110, hit["y"])
        card_region = (dl - 120, dt - 60, dr + 700, db + 200)
        name2, hit2 = self.wait_any(
            [("msg_button", card_region), ("add_button", card_region)],
            self.cfg.get("wait_ui_timeout", 8))
        if name2 is None:
            self.save_debug("no_card_{}".format(number))
            return None

        # 情形1:已是好友
        if name2 == "msg_button":
            self.click(dl + 80, dt + 45)  # 收起卡片
            return R_FRIEND

        # 情形2:可添加
        add_btn = hit2
        time.sleep(0.7)  # 等卡片动画结束

        if self.enable_tag:
            if not self._do_tagging(number, add_btn):
                return None
            add_btn = self.find("add_button", region=card_region)
            if add_btn is None:
                self.save_debug("no_addbtn2_{}".format(number))
                return None

        # 点「添加为联系人」
        self.click(add_btn["x"], add_btn["y"])

        # 验证语弹窗
        name4, _ = self.wait_any([("invite_send", None)], self.cfg.get("wait_ui_timeout", 8))
        if name4 is None:
            self.save_debug("no_invite_{}".format(number))
            return None
        time.sleep(0.4)
        sb = self.find("invite_send")
        if sb is None:
            self.save_debug("no_sendbtn_{}".format(number))
            return None

        # 填验证语
        if self.remark:
            if self.matcher.has("invite_input"):
                inp = self.find("invite_input")
                if inp:
                    self.click(inp["x"], inp["y"])
                else:
                    self.click(sb["x"] + INVITE_INPUT_OFFSET[0],
                               sb["y"] + int(INVITE_INPUT_OFFSET[1] * sb.get("scale", 1.0)))
            else:
                self.click(sb["x"] + INVITE_INPUT_OFFSET[0],
                           sb["y"] + int(INVITE_INPUT_OFFSET[1] * sb.get("scale", 1.0)))
            self.paste(self.remark)

        sb = self.find("invite_send") or sb
        self.click(sb["x"], sb["y"])
        if not self.wait_gone("invite_send", None, 8):
            self.save_debug("send_unconfirmed_{}".format(number))
            return None
        return ("SENT", R_SENT)

    # ================= 主循环 =================

    def run(self, limit=None, test_mode=False):
        path = self.cfg.get("input_file", "")
        if not path or not os.path.exists(path):
            self.log("找不到号码文件,请先在界面选择 txt。")
            return
        entries, enc = self.load_numbers(path)

        # 同号码继承已有结果
        known = {e["num"]: e["remark"] for e in entries if e["num"] and e["remark"]}
        for e in entries:
            if e["num"] and not e["remark"] and e["num"] in known:
                e["remark"] = known[e["num"]]
        self.write_numbers(path, entries, enc)

        pending, seen = [], set()
        for e in entries:
            if e["num"] and not e["remark"] and e["num"] not in seen:
                pending.append(e["num"])
                seen.add(e["num"])

        total_valid = len({e["num"] for e in entries if e["num"]})
        if limit is None:
            limit = len(pending)
        if test_mode:
            limit = min(limit, 3)

        hwnd, _ = self.dialog_rect()
        if hwnd is None:
            self.log("没找到「添加客户」弹窗。请在企业微信打开:通讯录 → 新的客户 → 添加,再开始。")
            return

        self.log("共 {} 个号码,待处理 {} 个;本次上限 {} 个号码 / {} 条好友请求。".format(
            total_valid, len(pending), limit, self.cap))
        self.log("5 秒后开始,运行中请勿操作鼠标键盘。紧急停止:鼠标甩到屏幕左上角,或点『停止』。")
        for _ in range(10):
            self._check_stop_soft()
            if self.stop_event and self.stop_event.is_set():
                self.log("已取消。")
                return
            time.sleep(0.5)

        sent = friends = invalid = unknown = done = 0
        consec_unknown = 0

        def emit():
            self.on_progress({"done": done, "pending": len(pending), "total": total_valid,
                              "sent": sent, "friends": friends, "invalid": invalid,
                              "unknown": unknown, "cap": self.cap})

        try:
            for i, num in enumerate(pending):
                if done >= limit:
                    break
                if sent >= self.cap:
                    self.log("已发出 {} 条好友请求,达到上限,自动停止。".format(sent))
                    break
                self._check_stop()
                self.log("[{}/{}] {} 处理中…".format(i + 1, len(pending), num))
                try:
                    result = self.process_one(num)
                except DialogGone:
                    self.log("『添加客户』弹窗不见了,停止。请重新打开该弹窗后再跑。")
                    break

                done += 1
                if result is None:
                    unknown += 1
                    consec_unknown += 1
                    self.log("  ⚠ 未知界面(已存 debug 截图),此号码留待下次重试。连续未知 {}。".format(consec_unknown))
                    if consec_unknown >= self.cfg.get("max_consecutive_unknown", 3):
                        self.log("连续多次未知状态,停止。可能界面有变化或触发频控——把 debug 截图发给作者可帮助修正。")
                        break
                else:
                    consec_unknown = 0
                    if isinstance(result, tuple) and result[0] == "SENT":
                        remark = result[1]
                        sent += 1
                        self.log("  ✓ {}(本次已发 {}/{})".format(remark, sent, self.cap))
                    else:
                        remark = result
                        self.log("  ✓ {}".format(remark))
                        if remark == R_FRIEND:
                            friends += 1
                        elif remark == R_INVALID:
                            invalid += 1
                    self.apply_result(entries, num, remark, path, enc)
                emit()

                if done < limit and sent < self.cap:
                    time.sleep(random.uniform(*self.delay))

        except StopRequested:
            self.log("已停止,进度已保存。")
        except pyautogui.FailSafeException:
            self.log("检测到鼠标甩到左上角,紧急停止,进度已保存。")

        self.log("本次结束:处理 {} | 已是好友 {} | 已发请求 {} | 无微信 {} | 未知 {}".format(
            done, friends, sent, invalid, unknown))
        emit()

    def _check_stop_soft(self):
        pass
