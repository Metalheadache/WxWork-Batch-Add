@echo off
REM ============================================================
REM  本地打包脚本(在 Windows 上运行,需已安装 Python 3.9+)
REM  双击本文件,或在命令行执行 build.bat
REM ============================================================
chcp 65001 >nul
setlocal

echo [1/3] 安装依赖...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

echo.
echo [2/3] 打包中(第一次较慢)...
python -m PyInstaller wxwork_batch_add.spec --noconfirm --clean

echo.
if exist "dist\WxWorkBatchAdd.exe" (
    echo [3/3] 完成!exe 在 dist\WxWorkBatchAdd.exe
) else (
    echo [3/3] 打包似乎失败,请检查上面的报错。
)
echo.
pause
