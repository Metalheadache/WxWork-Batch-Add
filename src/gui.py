# -*- coding: utf-8 -*-
"""图形界面(tkinter)。

后台线程跑引擎,线程通过队列把日志/进度回传到界面;界面用 after() 轮询队列,
从不在子线程里直接碰 tkinter。
"""

import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

import config as C
from manifest import required_names
from matcher import enable_dpi_awareness, TemplateMatcher, detect_system_scale
from calibration import CalibrationWizard
from engine import Engine


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("{}  v{}".format(C.APP_NAME, C.APP_VERSION))
        self.geometry("760x720")
        self.minsize(720, 640)

        self.cfg = C.load_config()
        self.q = queue.Queue()
        self.stop_event = threading.Event()
        self.worker = None

        self._build()
        self._ui_from_cfg()
        self._refresh_template_status()
        self.after(120, self._drain)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------- 布局 ----------------
    def _build(self):
        pad = {"padx": 10, "pady": 4}
        font = ("Microsoft YaHei", 10)

        # 号码文件
        f1 = tk.LabelFrame(self, text="① 号码文件（txt，每行一个 11 位手机号）", font=font)
        f1.pack(fill="x", **pad)
        self.var_file = tk.StringVar()
        tk.Entry(f1, textvariable=self.var_file, font=font).pack(side="left", fill="x",
                                                                 expand=True, padx=8, pady=8)
        tk.Button(f1, text="选择…", command=self._pick_file).pack(side="left", padx=8)

        # 标签
        f2 = tk.LabelFrame(self, text="② 标签（可选）", font=font)
        f2.pack(fill="x", **pad)
        self.var_enable_tag = tk.BooleanVar()
        tk.Checkbutton(f2, text="为新添加的联系人打标签", variable=self.var_enable_tag,
                       command=self._toggle_tag, font=font).pack(anchor="w", padx=8, pady=(6, 0))
        row = tk.Frame(f2)
        row.pack(fill="x", padx=28, pady=(2, 8))
        tk.Label(row, text="标签名称：", font=font).pack(side="left")
        self.var_tag = tk.StringVar()
        self.ent_tag = tk.Entry(row, textvariable=self.var_tag, font=font)
        self.ent_tag.pack(side="left", fill="x", expand=True)
        tk.Label(f2, text="（该标签需已存在于企业微信中；程序会在标签面板里搜索并选中它）",
                 fg="#777", font=("Microsoft YaHei", 9)).pack(anchor="w", padx=28, pady=(0, 6))

        # 验证语
        f3 = tk.LabelFrame(self, text="③ 好友验证语", font=font)
        f3.pack(fill="both", **pad)
        self.txt_remark = tk.Text(f3, height=3, font=font, wrap="word")
        self.txt_remark.pack(fill="both", expand=True, padx=8, pady=8)

        # 频控
        f4 = tk.LabelFrame(self, text="④ 频率与安全", font=font)
        f4.pack(fill="x", **pad)
        r = tk.Frame(f4)
        r.pack(fill="x", padx=8, pady=8)
        tk.Label(r, text="本次最多发送好友请求：", font=font).pack(side="left")
        self.var_cap = tk.IntVar()
        tk.Spinbox(r, from_=1, to=1000, textvariable=self.var_cap, width=6, font=font).pack(side="left")
        tk.Label(r, text="   每个号码间隔（秒）：", font=font).pack(side="left")
        self.var_dmin = tk.DoubleVar()
        self.var_dmax = tk.DoubleVar()
        tk.Spinbox(r, from_=1, to=120, textvariable=self.var_dmin, width=5, increment=1, font=font).pack(side="left")
        tk.Label(r, text="—", font=font).pack(side="left")
        tk.Spinbox(r, from_=1, to=120, textvariable=self.var_dmax, width=5, increment=1, font=font).pack(side="left")
        tk.Label(f4, text="建议 ≥ 8 秒并每天 ≤ 100 条，过快极易触发企业微信频控。",
                 fg="#a33", font=("Microsoft YaHei", 9)).pack(anchor="w", padx=8, pady=(0, 6))

        # 模板 / 校准
        f5 = tk.LabelFrame(self, text="⑤ 按钮识别（模板）", font=font)
        f5.pack(fill="x", **pad)
        self.lbl_tpl = tk.Label(f5, text="", font=font, anchor="w", justify="left")
        self.lbl_tpl.pack(fill="x", padx=8, pady=(8, 4))
        rr = tk.Frame(f5)
        rr.pack(fill="x", padx=8, pady=(0, 8))
        tk.Button(rr, text="校准向导（用自己的屏幕）", command=self._calibrate).pack(side="left")
        tk.Button(rr, text="自检模板", command=self._selfcheck).pack(side="left", padx=8)
        tk.Button(rr, text="用默认模板", command=self._use_default).pack(side="left")

        # 控制
        f6 = tk.Frame(self)
        f6.pack(fill="x", **pad)
        self.btn_start = tk.Button(f6, text="▶ 开始", width=12, command=self._start,
                                   bg="#2b7", fg="white", font=("Microsoft YaHei", 11, "bold"))
        self.btn_start.pack(side="left")
        self.btn_test = tk.Button(f6, text="试跑 3 个", command=lambda: self._start(test=True))
        self.btn_test.pack(side="left", padx=8)
        self.btn_stop = tk.Button(f6, text="■ 停止", width=10, command=self._stop, state="disabled")
        self.btn_stop.pack(side="left")
        self.lbl_stat = tk.Label(f6, text="", font=font)
        self.lbl_stat.pack(side="right")

        # 日志
        f7 = tk.LabelFrame(self, text="运行日志", font=font)
        f7.pack(fill="both", expand=True, **pad)
        self.log = scrolledtext.ScrolledText(f7, height=10, font=("Consolas", 9), state="disabled")
        self.log.pack(fill="both", expand=True, padx=6, pady=6)

    # ---------------- 配置 <-> 界面 ----------------
    def _ui_from_cfg(self):
        c = self.cfg
        self.var_file.set(c.get("input_file", ""))
        self.var_enable_tag.set(c.get("enable_tag", False))
        self.var_tag.set(c.get("tag_name", ""))
        self.txt_remark.delete("1.0", "end")
        self.txt_remark.insert("1.0", c.get("remark", ""))
        self.var_cap.set(int(c.get("daily_cap", 100)))
        self.var_dmin.set(float(c.get("delay_min", 8)))
        self.var_dmax.set(float(c.get("delay_max", 15)))
        self._toggle_tag()

    def _cfg_from_ui(self):
        c = self.cfg
        c["input_file"] = self.var_file.get().strip()
        c["enable_tag"] = bool(self.var_enable_tag.get())
        c["tag_name"] = self.var_tag.get().strip()
        c["remark"] = self.txt_remark.get("1.0", "end").strip()
        try:
            c["daily_cap"] = int(self.var_cap.get())
            c["delay_min"] = float(self.var_dmin.get())
            c["delay_max"] = float(self.var_dmax.get())
        except Exception:
            pass
        if c["delay_max"] < c["delay_min"]:
            c["delay_max"] = c["delay_min"]
        C.save_config(c)

    def _toggle_tag(self):
        state = "normal" if self.var_enable_tag.get() else "disabled"
        self.ent_tag.config(state=state)

    # ---------------- 模板状态 ----------------
    def _refresh_template_status(self):
        tdir = C.active_templates_dir(self.cfg)
        which = "自定义(校准)" if self.cfg.get("template_set") == "custom" else "默认(内置)"
        m = TemplateMatcher(tdir, self.cfg.get("threshold", 0.82))
        need = required_names(self.cfg.get("enable_tag", False))
        missing = [n for n in need if not m.has(n)]
        scale = detect_system_scale()
        info = "当前模板：{}   系统缩放：{:.0f}%".format(which, scale * 100)
        if missing:
            info += "\n⚠ 缺少 {} 个必需模板：{}\n建议点『校准向导』重新采集。".format(len(missing), "、".join(missing))
            self.lbl_tpl.config(fg="#a33")
        else:
            info += "\n✓ 必需模板齐全（{} 个）。".format(len(need))
            self.lbl_tpl.config(fg="#161")
        self.lbl_tpl.config(text=info)

    def _use_default(self):
        self.cfg["template_set"] = "default"
        C.save_config(self.cfg)
        self._refresh_template_status()
        self._append("已切换为默认内置模板。")

    def _selfcheck(self):
        self._cfg_from_ui()
        self._refresh_template_status()
        tdir = C.active_templates_dir(self.cfg)
        m = TemplateMatcher(tdir, self.cfg.get("threshold", 0.82))
        need = required_names(self.cfg.get("enable_tag", False))
        missing = [n for n in need if not m.has(n)]
        if missing:
            messagebox.showwarning("自检", "缺少必需模板:\n" + "、".join(missing) +
                                   "\n\n请运行校准向导采集。", parent=self)
        else:
            messagebox.showinfo("自检", "必需模板齐全,可以开始。\n\n"
                                "提示:开始前请手动打开\n企业微信 → 通讯录 → 新的客户 → 添加,\n"
                                "让『添加客户』搜索弹窗停在屏幕上。", parent=self)

    def _calibrate(self):
        self._cfg_from_ui()
        if not messagebox.askyesno(
                "校准向导",
                "校准会让你从自己的屏幕上框选每个按钮。\n\n"
                "开始前请先打开企业微信,并准备好在提示时切换到对应界面。\n\n现在开始?",
                parent=self):
            return

        def done(n):
            if n > 0:
                self.cfg["template_set"] = "custom"
                C.save_config(self.cfg)
            self._refresh_template_status()
            self._append("校准结束,保存 {} 个模板。".format(n))

        CalibrationWizard(self, C.CUSTOM_TEMPLATES_DIR,
                          self.cfg.get("enable_tag", False), on_done=done)

    # ---------------- 运行 ----------------
    def _pick_file(self):
        p = filedialog.askopenfilename(title="选择号码 txt",
                                       filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")])
        if p:
            self.var_file.set(p)

    def _start(self, test=False):
        if self.worker and self.worker.is_alive():
            return
        self._cfg_from_ui()
        c = self.cfg
        if not c["input_file"] or not os.path.exists(c["input_file"]):
            messagebox.showerror("缺少号码文件", "请先选择存在的 txt 号码文件。", parent=self)
            return
        if c["enable_tag"] and not c["tag_name"]:
            messagebox.showerror("缺少标签名", "已勾选打标签,请填写标签名称。", parent=self)
            return
        tdir = C.active_templates_dir(c)
        m = TemplateMatcher(tdir, c.get("threshold", 0.82))
        missing = [n for n in required_names(c["enable_tag"]) if not m.has(n)]
        if missing:
            messagebox.showerror("模板缺失", "缺少必需模板:\n" + "、".join(missing) +
                                 "\n\n请先运行校准向导。", parent=self)
            return
        if not messagebox.askyesno(
                "开始前确认",
                "请确认:\n"
                "1) 企业微信『添加客户』搜索弹窗已打开并停在屏幕上;\n"
                "2) 运行期间不要操作鼠标键盘;\n"
                "3) 紧急停止:鼠标甩到屏幕左上角,或点『停止』。\n\n现在开始?",
                parent=self):
            return

        self.stop_event.clear()
        self.btn_start.config(state="disabled")
        self.btn_test.config(state="disabled")
        self.btn_stop.config(state="normal")

        def on_log(s):
            self.q.put(("log", s))

        def on_prog(d):
            self.q.put(("prog", d))

        def work():
            try:
                eng = Engine(c, tdir, on_log=on_log, on_progress=on_prog, stop_event=self.stop_event)
                eng.run(test_mode=test)
            except Exception as ex:
                self.q.put(("log", "引擎异常: {}".format(ex)))
            finally:
                self.q.put(("done", None))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _stop(self):
        self.stop_event.set()
        self._append("正在停止…（当前号码处理完即停）")

    def _drain(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self._append(payload)
                elif kind == "prog":
                    d = payload
                    self.lbl_stat.config(text="已发 {}/{}  好友 {}  无微信 {}  未知 {}".format(
                        d.get("sent", 0), d.get("cap", 0), d.get("friends", 0),
                        d.get("invalid", 0), d.get("unknown", 0)))
                elif kind == "done":
                    self.btn_start.config(state="normal")
                    self.btn_test.config(state="normal")
                    self.btn_stop.config(state="disabled")
        except queue.Empty:
            pass
        self.after(120, self._drain)

    def _append(self, s):
        self.log.config(state="normal")
        self.log.insert("end", s + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def _on_close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("退出", "任务还在运行,确定退出?", parent=self):
                return
            self.stop_event.set()
        self._cfg_from_ui()
        self.destroy()


def main():
    enable_dpi_awareness()
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
