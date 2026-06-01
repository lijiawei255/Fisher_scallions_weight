"""
程序入口。

Windows 上全屏需要管理员权限（focus stealing 等限制），
启动时尝试以管理员身份自动重启一次。
"""
from __future__ import annotations

import sys
import tkinter as tk

from app import WeightApp, run_as_admin, is_admin


def main() -> None:
    if sys.platform == "win32":
        try:
            run_as_admin()
        except Exception as e:
            print(f"[警告] 管理员权限请求失败: {e}", file=sys.stderr)

    root = tk.Tk()
    # 全局设置仿宋字体
    try:
        root.option_add("*Font", "仿宋 10")
    except tk.TclError:
        pass
    app = WeightApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
