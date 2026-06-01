"""
打包脚本：把项目打包成单 exe（Windows GUI 程序）

用法:
    python build.py

产物:
    dist/葱称重系统.exe  (单文件，约 15-20MB)

技术细节:
- 使用 PyInstaller 6.x
- --onefile: 打包成单 exe
- --windowed: 无控制台窗口（GUI 程序）
- --icon: 程序图标
- --add-data: 嵌入校徽.png (PyInstaller 会解压到 sys._MEIPASS)
- --name: 产物名
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
EXE_NAME = "葱称重系统"
ICON_PATH = PROJECT_DIR / "tubiao.ico"
LOGO_PATH = PROJECT_DIR / "校徽.png"


def clean() -> None:
    """清理旧产物。"""
    for d in ("build", "dist"):
        p = PROJECT_DIR / d
        if p.exists():
            print(f"[清理] 删除 {p}")
            shutil.rmtree(p)
    # 清理 .spec
    for spec in PROJECT_DIR.glob("*.spec"):
        print(f"[清理] 删除 {spec}")
        spec.unlink()


def build() -> None:
    """执行 PyInstaller 打包。"""
    if not ICON_PATH.exists():
        print(f"[警告] 图标文件不存在: {ICON_PATH}")
        print("       继续打包但不使用自定义图标")

    if not LOGO_PATH.exists():
        print(f"[警告] 校徽图片不存在: {LOGO_PATH}")
        print("       运行时 GUI 会回退到纯文字 LOGO")

    # Windows 下 PyInstaller 用 ; 分隔多文件路径
    sep = ";" if sys.platform == "win32" else ":"
    add_data_args = []
    if LOGO_PATH.exists():
        add_data_args.extend(["--add-data", f"{LOGO_PATH}{sep}."])

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name", EXE_NAME,
        "--icon", str(ICON_PATH) if ICON_PATH.exists() else "NONE",
        *add_data_args,
        str(PROJECT_DIR / "main.py"),
    ]
    cmd = [c for c in cmd if c != "NONE"]  # 去掉占位符

    print("[执行]", " ".join(cmd))
    result = subprocess.run(cmd, cwd=PROJECT_DIR)
    if result.returncode != 0:
        print(f"[失败] PyInstaller 返回 {result.returncode}")
        sys.exit(result.returncode)

    exe = PROJECT_DIR / "dist" / f"{EXE_NAME}.exe"
    if exe.exists():
        size_mb = exe.stat().st_size / (1024 * 1024)
        print(f"\n[成功] 产物: {exe}")
        print(f"       大小: {size_mb:.1f} MB")
    else:
        print(f"[失败] 未找到 {exe}")
        sys.exit(1)


if __name__ == "__main__":
    clean()
    build()
