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
        # 取消之前的动画
        if self._animation_id is not None:
            self.label.after_cancel(self._animation_id)
            self._animation_id = None

        self._start_value = self._current_value
        self._target_value = new_target
        self._start_time = time.time()

        # 如果差异很小，直接显示
        if abs(new_target - self._current_value) < 0.5:
            self._current_value = new_target
            self.label.config(text=f"{int(new_target)}")
            return

        # 变化瞬间：高亮
        self.label.config(fg=self.color_active)
        if self._settle_timer is not None:
            self.label.after_cancel(self._settle_timer)
            self._settle_timer = None
        self._settle_timer = self.label.after(self.duration_ms, self._on_settle)

        self._animate()

    def _on_settle(self) -> None:
        """动画结束后恢复稳定颜色。"""
        self.label.config(fg=self.color_stable)
        self._settle_timer = None

    def _animate(self) -> None:
        """动画循环（约 60fps）。"""
        elapsed = (time.time() - self._start_time) * 1000  # ms
        progress = min(elapsed / self.duration_ms, 1.0)

        # ease-out cubic: 1 - (1 - t)³
        eased = 1 - pow(1 - progress, 3)
        self._current_value = self._start_value + (self._target_value - self._start_value) * eased

        self.label.config(text=f"{int(self._current_value)}")

        if progress < 1.0:
            self._animation_id = self.label.after(16, self._animate)  # ~60fps
        else:
            self._current_value = self._target_value
            self.label.config(text=f"{int(self._target_value)}")
            self._animation_id = None
