"""
Apple 风格平滑数字动画组件。

核心特性：
- ease-out cubic 缓动，数字变化先快后慢
- 颜色跟随：变化时高亮（浅亮绿），稳定后恢复（祖母绿）
"""

from __future__ import annotations

import time
import tkinter as tk
from typing import Optional


class SmoothNumberAnimator:
    """管理单个数字的平滑动画，带颜色跟随效果。"""

    def __init__(
        self,
        label: tk.Label,
        duration_ms: int = 400,
        color_stable: str = "#059669",
        color_active: str = "#34d399",
    ):
        self.label = label
        self.duration_ms = duration_ms
        self.color_stable = color_stable
        self.color_active = color_active

        self._current_value = 0.0
        self._target_value = 0.0
        self._start_value = 0.0
        self._start_time = 0.0
        self._animation_id: Optional[str] = None
        self._settle_timer: Optional[str] = None

    def set_value(self, new_target: float) -> None:
        """设置新目标值，自动触发动画。"""
        # 安全：取消旧动画时 Label 可能已被销毁（主窗口关闭）
        if self._animation_id is not None:
            try:
                self.label.after_cancel(self._animation_id)
            except tk.TclError:
                pass
            self._animation_id = None

        self._start_value = self._current_value
        self._target_value = new_target
        self._start_time = time.time()

        # 如果差异很小，直接显示
        if abs(new_target - self._current_value) < 0.5:
            self._current_value = new_target
            try:
                self.label.config(text=f"{int(new_target)}")
            except tk.TclError:
                pass
            return

        # 变化瞬间：高亮
        try:
            self.label.config(fg=self.color_active)
        except tk.TclError:
            return
        if self._settle_timer is not None:
            try:
                self.label.after_cancel(self._settle_timer)
            except tk.TclError:
                pass
            self._settle_timer = None
        self._settle_timer = self.label.after(self.duration_ms, self._on_settle)

        self._animate()

    def _on_settle(self) -> None:
        """动画结束后恢复稳定颜色。"""
        self._settle_timer = None
        try:
            self.label.config(fg=self.color_stable)
        except tk.TclError:
            pass  # 窗口已被销毁

    def _animate(self) -> None:
        """动画循环（约 60fps）。"""
        elapsed = (time.time() - self._start_time) * 1000  # ms
        progress = min(elapsed / self.duration_ms, 1.0)

        # ease-out cubic: 1 - (1 - t)³
        eased = 1 - pow(1 - progress, 3)
        self._current_value = self._start_value + (self._target_value - self._start_value) * eased

        try:
            self.label.config(text=f"{int(self._current_value)}")
        except tk.TclError:
            self._animation_id = None
            return  # 窗口已被销毁，停止动画

        if progress < 1.0:
            self._animation_id = self.label.after(16, self._animate)  # ~60fps
        else:
            self._current_value = self._target_value
            self.label.config(text=f"{int(self._target_value)}")
            self._animation_id = None
