# -*- coding: utf-8 -*-
"""校准向导。

让每个用户从『自己的屏幕』上框选出各个按钮,保存成个人模板。
因为模板与运行环境同源,主题(深/浅色)、分辨率、企业微信版本、语言都不再是问题——
这是本工具能被『别人』用起来的关键。

实现要点:
  - 截取整屏(主显示器),按比例缩放显示在画布上;
  - 用户拖拽选框;把画布坐标映射回『全分辨率』截图再裁剪保存,
    从而彻底绕开 tkinter 的逻辑像素/DPI 问题(运行时也用同样的全分辨率截图匹配)。
"""

import os
import json
import time
import tkinter as tk
from tkinter import messagebox

import numpy as np
from PIL import Image, ImageTk, ImageGrab

from manifest import specs_for


MAX_CANVAS_W = 1280
MAX_CANVAS_H = 720


class CalibrationWizard(tk.Toplevel):
    def __init__(self, master, save_dir, enable_tag, on_done=None):
        super().__init__(master)
        self.title("校准向导 — 从你自己的屏幕框选按钮")
        self.save_dir = save_dir
        self.on_done = on_done
        self.specs = specs_for(enable_tag, include_optional=True)
        self.idx = 0
        self.saved = 0
        self.geometry = {}   # name -> [cx, cy] 全分辨率中心,用于推算标签偏移

        os.makedirs(self.save_dir, exist_ok=True)

        self._shot_full = None      # 全分辨率截图 (PIL)
        self._shot_scale = 1.0      # 显示缩放
        self._tkimg = None
        self._rect = None
        self._start = None

        self._build()
        self._show_step()
        self.grab_set()

    # -- 布局 --------------------------------------------------------------
    def _build(self):
        top = tk.Frame(self, padx=12, pady=10)
        top.pack(fill="x")
        self.lbl_step = tk.Label(top, font=("Microsoft YaHei", 13, "bold"), anchor="w")
        self.lbl_step.pack(fill="x")
        self.lbl_hint = tk.Label(top, font=("Microsoft YaHei", 10), fg="#444",
                                 wraplength=MAX_CANVAS_W, justify="left", anchor="w")
        self.lbl_hint.pack(fill="x", pady=(4, 0))

        self.canvas = tk.Canvas(self, width=MAX_CANVAS_W, height=MAX_CANVAS_H,
                                bg="#111", highlightthickness=1, highlightbackground="#888",
                                cursor="crosshair")
        self.canvas.pack(padx=12, pady=8)
        self.canvas.bind("<ButtonPress-1>", self._on_down)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_up)

        bar = tk.Frame(self, padx=12, pady=10)
        bar.pack(fill="x")
        self.btn_shot = tk.Button(bar, text="① 截图（把企业微信调到对应界面后点这里）",
                                  command=self._recapture, height=1)
        self.btn_shot.pack(side="left")
        self.btn_skip = tk.Button(bar, text="跳过此项", command=self._skip)
        self.btn_skip.pack(side="right")
        self.btn_next = tk.Button(bar, text="② 保存并下一步 ▶", command=self._save_next,
                                  state="disabled")
        self.btn_next.pack(side="right", padx=8)
        tk.Button(bar, text="退出", command=self._quit).pack(side="right")

    # -- 步骤显示 ----------------------------------------------------------
    def _show_step(self):
        spec = self.specs[self.idx]
        self.lbl_step.config(
            text="第 {}/{} 步：{}  [{}]".format(
                self.idx + 1, len(self.specs), spec["label"],
                "可跳过" if spec["group"] == "optional" else "必需"))
        self.lbl_hint.config(text=spec["hint"])
        self.btn_skip.config(state="normal" if spec["group"] == "optional" else "disabled")
        self.btn_next.config(state="disabled")
        self._clear_rect()

    # -- 截图 --------------------------------------------------------------
    def _recapture(self):
        self.iconify()          # 收起向导,露出后面的企业微信
        self.update()
        time.sleep(0.9)
        try:
            shot = ImageGrab.grab()  # 主显示器,全分辨率
        finally:
            self.deiconify()
            self.lift()
        self._shot_full = shot.convert("RGB")
        W, H = self._shot_full.size
        self._shot_scale = min(MAX_CANVAS_W / W, MAX_CANVAS_H / H, 1.0)
        disp = self._shot_full.resize(
            (max(1, int(W * self._shot_scale)), max(1, int(H * self._shot_scale))),
            Image.LANCZOS)
        self._tkimg = ImageTk.PhotoImage(disp)
        self.canvas.delete("all")
        self.canvas.config(width=disp.width, height=disp.height)
        self.canvas.create_image(0, 0, anchor="nw", image=self._tkimg)
        self._rect = None
        self._start = None

    # -- 拖拽选框 ----------------------------------------------------------
    def _on_down(self, e):
        if self._shot_full is None:
            return
        self._start = (e.x, e.y)
        self._clear_rect()
        self._rect = self.canvas.create_rectangle(e.x, e.y, e.x, e.y,
                                                  outline="#ff3b30", width=2)

    def _on_drag(self, e):
        if self._rect and self._start:
            self.canvas.coords(self._rect, self._start[0], self._start[1], e.x, e.y)

    def _on_up(self, e):
        if self._rect and self._start:
            x1, y1 = self._start
            x2, y2 = e.x, e.y
            if abs(x2 - x1) >= 6 and abs(y2 - y1) >= 6:
                self.btn_next.config(state="normal")
            else:
                self._clear_rect()

    def _clear_rect(self):
        if self._rect:
            self.canvas.delete(self._rect)
            self._rect = None

    # -- 保存 --------------------------------------------------------------
    def _current_box_fullres(self):
        if not self._rect:
            return None
        x1, y1, x2, y2 = self.canvas.coords(self._rect)
        x1, x2 = sorted((x1, x2))
        y1, y2 = sorted((y1, y2))
        s = self._shot_scale
        fx1, fy1 = int(x1 / s), int(y1 / s)
        fx2, fy2 = int(x2 / s), int(y2 / s)
        W, H = self._shot_full.size
        fx1, fy1 = max(0, fx1), max(0, fy1)
        fx2, fy2 = min(W, fx2), min(H, fy2)
        if fx2 - fx1 < 4 or fy2 - fy1 < 4:
            return None
        return (fx1, fy1, fx2, fy2)

    def _save_next(self):
        box = self._current_box_fullres()
        if box is None:
            messagebox.showwarning("提示", "选框太小,请重新框选。", parent=self)
            return
        spec = self.specs[self.idx]
        crop = self._shot_full.crop(box)
        path = os.path.join(self.save_dir, spec["name"] + ".png")
        try:
            crop.save(path)
            self.saved += 1
            self.geometry[spec["name"]] = [(box[0] + box[2]) // 2, (box[1] + box[3]) // 2]
        except Exception as ex:
            messagebox.showerror("保存失败", str(ex), parent=self)
            return
        self._advance()

    def _skip(self):
        self._advance()

    def _advance(self):
        self.idx += 1
        if self.idx >= len(self.specs):
            self._finish()
        else:
            # 保留上一张截图,方便同一界面连续框选多个元素
            keep = self._shot_full is not None
            self._show_step()
            if keep:
                self._redraw_kept()

    def _redraw_kept(self):
        if self._tkimg is not None:
            self.canvas.delete("all")
            self.canvas.create_image(0, 0, anchor="nw", image=self._tkimg)

    def _finish(self):
        # 写出几何信息(标签偏移推算用),仅当搜索框与第一个标签在同一次校准中采集
        if "panel_search" in self.geometry and "panel_first_chip" in self.geometry:
            try:
                with open(os.path.join(self.save_dir, "geometry.json"), "w", encoding="utf-8") as f:
                    json.dump({"panel_search": self.geometry["panel_search"],
                               "panel_first_chip": self.geometry["panel_first_chip"]},
                              f, ensure_ascii=False, indent=2)
            except Exception:
                pass
        messagebox.showinfo(
            "完成", "校准完成,已保存 {} 个模板到:\n{}\n\n程序将改用你的自定义模板运行。".format(
                self.saved, self.save_dir), parent=self)
        if self.on_done:
            self.on_done(self.saved)
        self.destroy()

    def _quit(self):
        if messagebox.askyesno("退出", "确定退出校准?已保存的模板会保留。", parent=self):
            if self.on_done:
                self.on_done(self.saved)
            self.destroy()


if __name__ == "__main__":
    # 独立调试:python calibration.py
    from matcher import enable_dpi_awareness
    enable_dpi_awareness()
    root = tk.Tk()
    root.withdraw()
    CalibrationWizard(root, os.path.join(os.path.dirname(__file__), "templates", "custom"),
                      enable_tag=True, on_done=lambda n: root.quit())
    root.mainloop()
