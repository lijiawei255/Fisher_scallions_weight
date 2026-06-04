"""
业务状态机：IDLE / WEIGHING 切换 + 累计总重。

设计原则：
- 重量首次稳定时立即锁定，之后不再更新
  → 推板下压发生在稳定之后，锁定的重量不受影响
- 进入 WEIGHING 需连续 N 次 > 高阈值，防误触发
- 退出 WEIGHING 需连续 M 次 < 低阈值，防抖
"""
from __future__ import annotations

from typing import Optional

import config


class WeightAccumulator:
    """大葱称重业务状态机。

    称重流程：
    1. 物体掉落到秤上 → 硬件值上升 → 进入 WEIGHING
    2. 硬件值稳定 → 显示值稳定 → 锁定锁定重量（locked_weight）
    3. 推板推走物体（可能下压导致读数升高）→ 锁定重量不变
    4. 物体离开 → 硬件值下降 → 退出 WEIGHING → locked_weight 计入总重
    """

    def __init__(self) -> None:
        self.state: str = "IDLE"  # IDLE | WEIGHING
        self.total_weight: float = 0.0
        self.locked_weight: float = 0.0  # 锁定重量：首次稳定时确定，之后不变
        self._locked: bool = False       # 是否已锁定
        self._enter_streak: int = 0      # 连续高于阈值的次数
        self._exit_streak: int = 0       # 连续低于阈值的次数
        self._last_event: Optional[dict] = None

    def update(self, filtered_grams: float, display_grams: float = 0.0) -> Optional[dict]:
        """输入硬件返回值和当前显示值，返回累计事件或 None。

        filtered_grams: 硬件返回值（硬件已滤波），用于状态机阈值判定。
        display_grams: 稳定判定后的显示值，用于锁定到总重。

        事件结构: {"event": "item_weighed", "weight_g": float}
        """
        v = float(filtered_grams)

        if self.state == "IDLE":
            if v > config.WEIGHT_THRESH_HIGH:
                self._enter_streak += 1
                self._exit_streak = 0
                if self._enter_streak >= config.ENTER_WEIGHING_STREAK:
                    self.state = "WEIGHING"
                    self._locked = False
                    self.locked_weight = 0.0
                    self._exit_streak = 0
            else:
                self._enter_streak = 0

        elif self.state == "WEIGHING":
            # 首次显示稳定时锁定重量，之后不再更新
            # 推板下压发生在稳定之后，锁定的重量不受影响
            if not self._locked and display_grams > 0:
                self.locked_weight = display_grams
                self._locked = True

            if v < config.WEIGHT_THRESH_LOW:
                self._exit_streak += 1
                self._enter_streak = 0
                if self._exit_streak >= config.EXIT_WEIGHING_STREAK:
                    # 物品离场：用锁定重量累计到总重
                    added = round(self.locked_weight)
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
                    self.locked_weight = 0.0
                    self._locked = False
                    self._exit_streak = 0
                    return event
            else:
                self._exit_streak = 0
        return None

    def clear_total(self) -> None:
        self.total_weight = 0.0
        self.state = "IDLE"
        self.locked_weight = 0.0
        self._locked = False
        self._enter_streak = 0
        self._exit_streak = 0

    def pop_event(self) -> Optional[dict]:
        e, self._last_event = self._last_event, None
        return e
