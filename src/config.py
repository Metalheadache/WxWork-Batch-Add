# -*- coding: utf-8 -*-
"""配置与路径管理。

- 处理 PyInstaller 打包后与源码运行两种情况下的资源路径。
- 用户配置以 JSON 形式保存在 exe 同级目录,方便携带与手改。
"""

import os
import sys
import json

APP_NAME = "企微批量添加助手"
APP_VERSION = "1.0.0"

# ---- 路径 ----------------------------------------------------------------


def resource_path(*parts):
    """只读资源(默认模板、图标)的路径,兼容 PyInstaller onefile。"""
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS  # PyInstaller 解包目录
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, *parts)


def app_dir():
    """可写数据目录:exe 所在目录(打包)或项目根目录(源码)。

    配置、日志、自定义模板、debug 截图都放这里。
    """
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return base


def user_path(*parts):
    p = os.path.join(app_dir(), *parts)
    return p


DEFAULT_TEMPLATES_DIR = resource_path("templates", "default")
CUSTOM_TEMPLATES_DIR = user_path("src", "templates", "custom") if not getattr(sys, "frozen", False) \
    else user_path("custom_templates")
CONFIG_FILE = user_path("config.json")
LOG_FILE = user_path("run.log")
DEBUG_DIR = user_path("debug")


# ---- 默认配置 ------------------------------------------------------------

DEFAULTS = {
    # 号码文件(txt)
    "input_file": "",
    # 标签
    "enable_tag": True,
    "tag_name": "",
    # 好友验证语
    "remark": "你好，我是XX的官方运营，添加我的企业微信与我联系吧。",
    # 频控 / 安全
    "daily_cap": 100,          # 本次运行最多发出的好友请求数
    "delay_min": 8.0,          # 每个号码之间随机等待下限(秒)
    "delay_max": 15.0,         # 上限
    # 匹配
    "template_set": "default",  # "default" 或 "custom"
    "threshold": 0.82,          # 模板匹配阈值
    "dpi_scale": 0.0,           # 0 = 自动检测;>0 = 手动指定(默认模板相对用户屏幕的缩放)
    # 超时
    "wait_result_timeout": 12,
    "wait_ui_timeout": 8,
    "max_consecutive_unknown": 3,
}


def load_config():
    cfg = dict(DEFAULTS)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            for k, v in saved.items():
                if k in cfg:
                    cfg[k] = v
        except Exception:
            pass  # 配置损坏则回退默认
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def active_templates_dir(cfg):
    if cfg.get("template_set") == "custom":
        return CUSTOM_TEMPLATES_DIR
    return DEFAULT_TEMPLATES_DIR
