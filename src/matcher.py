# -*- coding: utf-8 -*-
"""多尺度、DPI 感知的模板匹配。

为什么需要多尺度:
  cv2.matchTemplate 对尺寸不具备不变性。默认模板是在某个分辨率/缩放下截取的,
  换一台机器(不同分辨率或系统缩放)时,同一个按钮在屏幕上的像素尺寸不同,
  单尺度匹配就会失败。这里在一组候选缩放上分别匹配,取最优。

  如果用户用「校准向导」截取了自己屏幕上的按钮,模板与运行环境同源,
  缩放≈1.0,匹配几乎精确;多尺度只是额外的容错。
"""

import os
import ctypes
import base64
import numpy as np
import cv2
from PIL import ImageGrab


def enable_dpi_awareness():
    """必须在任何截图/坐标操作前调用,保证坐标 == 物理像素。"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def detect_system_scale():
    """返回系统主屏缩放系数(1.0 / 1.25 / 1.5 ...)。失败返回 1.0。"""
    try:
        hdc = ctypes.windll.user32.GetDC(0)
        LOGPIXELSX = 88
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, LOGPIXELSX)
        ctypes.windll.user32.ReleaseDC(0, hdc)
        if dpi > 0:
            return dpi / 96.0
    except Exception:
        pass
    return 1.0


def grab_screen():
    """整屏截图,返回 BGR ndarray。"""
    im = ImageGrab.grab()
    return cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)


def imread_unicode(path):
    """兼容中文路径，并支持仓库内的 Base64 文本模板。"""
    if path.lower().endswith(".b64"):
        with open(path, "r", encoding="ascii") as f:
            raw = base64.b64decode(f.read())
        data = np.frombuffer(raw, dtype=np.uint8)
    else:
        data = np.fromfile(path, dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


class TemplateMatcher:
    def __init__(self, templates_dir, threshold=0.82, base_scale=1.0):
        """
        base_scale: 默认模板相对当前屏幕的整体缩放先验。
                    例如默认模板截于 150% 屏,用户是 100% 屏,则用户屏上按钮更小,
                    base_scale ≈ 100/150 = 0.667。校准模板同源时 base_scale=1.0。
        """
        self.dir = templates_dir
        self.threshold = threshold
        self.base_scale = base_scale if base_scale and base_scale > 0 else 1.0
        self._cache = {}   # name -> BGR ndarray
        self._loaded = self._scan()

    # -- 模板加载 ----------------------------------------------------------
    def _scan(self):
        found = {}
        if os.path.isdir(self.dir):
            for fn in os.listdir(self.dir):
                lower = fn.lower()
                if lower.endswith(".png"):
                    found[fn[:-4]] = os.path.join(self.dir, fn)
                elif lower.endswith(".png.b64"):
                    found[fn[:-8]] = os.path.join(self.dir, fn)
        return found

    def has(self, name):
        return name in self._loaded

    def available(self):
        return sorted(self._loaded.keys())

    def _template(self, name):
        if name not in self._cache:
            if name not in self._loaded:
                return None
            img = imread_unicode(self._loaded[name])
            self._cache[name] = img
        return self._cache[name]

    # -- 匹配 --------------------------------------------------------------
    def _scales(self):
        b = self.base_scale
        # 在先验缩放附近搜索一圈,兼顾轻微渲染差异
        rel = [1.0, 0.92, 1.08, 0.85, 1.15, 0.75, 1.25]
        seen, out = set(), []
        for r in rel:
            s = round(b * r, 3)
            if s not in seen and s > 0.2:
                seen.add(s)
                out.append(s)
        return out

    def find(self, name, screen=None, region=None, threshold=None):
        """在屏幕(或 region 子区域)中查找模板。

        返回 dict(score, x, y, w, h, scale) 或 None。x,y 为匹配中心(屏幕坐标)。
        """
        tpl0 = self._template(name)
        if tpl0 is None:
            return None
        if screen is None:
            screen = grab_screen()
        th = self.threshold if threshold is None else threshold

        x0, y0 = 0, 0
        area = screen
        if region:
            H, W = screen.shape[:2]
            x1, y1, x2, y2 = region
            x1, y1 = max(0, int(x1)), max(0, int(y1))
            x2, y2 = min(W, int(x2)), min(H, int(y2))
            if x2 - x1 < 8 or y2 - y1 < 8:
                return None
            area = screen[y1:y2, x1:x2]
            x0, y0 = x1, y1

        best = None
        for s in self._scales():
            if abs(s - 1.0) < 1e-3:
                tpl = tpl0
            else:
                nw = max(8, int(tpl0.shape[1] * s))
                nh = max(8, int(tpl0.shape[0] * s))
                interp = cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR
                tpl = cv2.resize(tpl0, (nw, nh), interpolation=interp)
            if area.shape[0] < tpl.shape[0] or area.shape[1] < tpl.shape[1]:
                continue
            res = cv2.matchTemplate(area, tpl, cv2.TM_CCOEFF_NORMED)
            _, score, _, loc = cv2.minMaxLoc(res)
            if best is None or score > best["score"]:
                best = {
                    "score": float(score),
                    "x": x0 + loc[0] + tpl.shape[1] // 2,
                    "y": y0 + loc[1] + tpl.shape[0] // 2,
                    "w": tpl.shape[1],
                    "h": tpl.shape[0],
                    "scale": s,
                }
            # 命中很高时提前退出,省时间
            if best and best["score"] >= 0.97:
                break
        if best and best["score"] >= th:
            return best
        return None
