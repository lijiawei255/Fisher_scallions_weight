"""
业务状态机：IDLE / WEIGHING 切换 + 累计总重。

设计原则：
- 总重累计使用显示值（stable judge 输出），而非峰值
  → 保证"总重增量 = 用户屏幕上看到的值"
- 进入 WEIGHING 需连续 N 次 > 高阈值，防误触发
- 退出 WEIGHING 需连续 M 次 < 低阈值，防抖
"""
from __future__ import annotations

from typing import Optional

import config


class WeightAccumulator:
    """大葱称重业务状态机。"""

    def __init__(self) -> None:
        self.state: str = "IDLE"  # IDLE | WEIGHING
        self.total_weight: float = 0.0
        self.last_stable_grams: float = 0.0  # 称重期间记录的显示值
        self._enter_streak: int = 0   # 连续高于阈值的次数
        self._exit_streak: int = 0    # 连续低于阈值的次数
        self._last_event: Optional[dict] = None

    def update(self, filtered_grams: float, display_grams: float = 0.0) -> Optional[dict]:
        """输入滤波后的 g 值和当前显示值，返回累计事件或 None。

        filtered_grams: 中值+平均滤波后的值，用于状态机阈值判定。
        display_grams: 稳定判定后的显示值，用于累计到总重。

        事件结构: {"event": "item_weighed"}
        """
        v = float(filtered_grams)

        if self.state == "IDLE":
            if v > config.WEIGHT_THRESH_HIGH:
                self._enter_streak += 1
                self._exit_streak = 0
                if self._enter_streak >= config.ENTER_WEIGHING_STREAK:
                    self.state = "WEIGHING"
                    self.last_stable_grams = display_grams
                    self._exit_streak = 0  # 重置退出计数，防止沿用旧值提前触发离场
            else:
                self._enter_streak = 0

        elif self.state == "WEIGHING":
            # 追踪称重期间的最高显示值（用户看到的最大值）
            # 不用原始峰值，而是用经过稳定判定的显示值，确保总重 = 显示值
            if display_grams > self.last_stable_grams:
                self.last_stable_grams = display_grams

            if v < config.WEIGHT_THRESH_LOW:
                self._exit_streak += 1
                self._enter_streak = 0
                if self._exit_streak >= config.EXIT_WEIGHING_STREAK:
                    # 物品离场：用显示值累计到总重
                    added = round(self.last_stable_grams)
                    event = None
                    if added > 0:
                        self.total_weight += added
                        if self.total_weight > config.MAX_TOTAL_GRAMS:
                            self.total_weight = config.MAX_TOTAL_GRAMS
                        event = {
                            "event": "item_weighed",
                            "weight_g": float(added),
                        }
                        self._last_event = event
                    # 重置
                    self.state = "IDLE"
                    self.last_stable_grams = 0.0
                    self._exit_streak = 0
                    return event
            else:
                self._exit_streak = 0
        return None

    def clear_total(self) -> None:
        self.total_weight = 0.0
        self.state = "IDLE"
        self.last_stable_grams = 0.0
        self._enter_streak = 0
        self._exit_streak = 0

    def pop_event(self) -> Optional[dict]:
        e, self._last_event = self._last_event, None
        return e
