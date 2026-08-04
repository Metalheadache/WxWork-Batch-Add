# -*- coding: utf-8 -*-
"""程序入口。

  python src/main.py        启动图形界面
双击打包后的 exe 也走这里。
"""

import sys
import os

# 让 PyInstaller 与源码运行都能 import 到同目录模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui import main

if __name__ == "__main__":
    main()
