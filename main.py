"""
程序入口。
"""
from __future__ import annotations

import sys
import tkinter as tk

from app import WeightApp


def main() -> None:
    root = tk.Tk()
    # Apple 风格：使用更现代的字体
    try:
        root.option_add("*Font", ("Microsoft YaHei", 10))
    except tk.TclError:
        pass
    app = WeightApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
