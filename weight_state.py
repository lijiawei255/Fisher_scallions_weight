"""
业务状态机：IDLE / WEIGHING 切换 + 累计总重。

优化点（相对 v2）:
- 进入 WEIGHING 需连续 N 次 > 高阈值，防误触发
- 退出 WEIGHING 需连续 M 次 < 低阈值，防抖
- 同一物品内更新 peak_weight，退出 WEIGHING 才计入总重
- 提供峰值回放，便于 UI 显示
"""
from __future__ import annotations

from typing import Optional

import config


class WeightAccumulator:
    """大葱称重业务状态机。"""

    def __init__(self) -> None:
        self.state: str = "IDLE"  # IDLE | WEIGHING
        self.peak_weight: float = 0.0
        self.total_weight: float = 0.0
        self.event_count: int = 0   # 累计件数（每次物品离场 +1）
        self._enter_streak: int = 0   # 连续高于阈值的次数
        self._exit_streak: int = 0    # 连续低于阈值的次数
        self._last_event: Optional[dict] = None

    def update(self, filtered_grams: float) -> Optional[dict]:
        """输入滤波后的 g 值，返回累计事件或 None。

        事件结构: {"event": "item_weighed", "weight_g": float, "peak_g": float}
        """
        v = float(filtered_grams)

        if self.state == "IDLE":
            if v > config.WEIGHT_THRESH_HIGH:
                self._enter_streak += 1
                self._exit_streak = 0
                if self._enter_streak >= config.ENTER_WEIGHING_STREAK:
                    self.state = "WEIGHING"
                    self.peak_weight = v
                    self._enter_streak = 0
            else:
                self._enter_streak = 0

        elif self.state == "WEIGHING":
            if v > self.peak_weight:
                self.peak_weight = v
                self._enter_streak = max(1, self._enter_streak)
            if v < config.WEIGHT_THRESH_LOW:
                self._exit_streak += 1
                self._enter_streak = 0
                if self._exit_streak >= config.EXIT_WEIGHING_STREAK:
                    # 物品离开，累计 peak 到总重
                    added = int(round(self.peak_weight))
                    if added > 0:
                        self.total_weight += added
                        self.event_count += 1
                        if self.total_weight > config.MAX_TOTAL_GRAMS:
                            self.total_weight = config.MAX_TOTAL_GRAMS
                        event = {
                            "event": "item_weighed",
                            "weight_g": float(added),
                            "peak_g": float(self.peak_weight),
                        }
                        self._last_event = event
                    # 重置
                    self.state = "IDLE"
                    self.peak_weight = 0.0
                    self._exit_streak = 0
                    return event
            else:
                self._exit_streak = 0
        return None

    def clear_total(self) -> None:
        self.total_weight = 0.0
        self.event_count = 0
        self.state = "IDLE"
        self.peak_weight = 0.0
        self._enter_streak = 0
        self._exit_streak = 0

    def pop_event(self) -> Optional[dict]:
        e, self._last_event = self._last_event, None
        return e
