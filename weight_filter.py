"""
滤波层：滑动平均 + 稳定值判定。

- MovingAverageFilter: deque 实现，超出窗口后丢弃最旧。
- StableJudge: 连续 N 次变化 < 阈值才确认稳定，避免数字跳变。
"""
from __future__ import annotations

import collections
from typing import Tuple


class MovingAverageFilter:
    """滑动平均滤波。"""

    def __init__(self, window_size: int = 5) -> None:
        if window_size < 1:
            raise ValueError("window_size 必须 >= 1")
        self._buf: collections.deque = collections.deque(maxlen=window_size)
        self.window_size = window_size

    def update(self, value: float) -> float:
        self._buf.append(float(value))
        if not self._buf:
            return 0.0
        return sum(self._buf) / len(self._buf)

    def reset(self) -> None:
        self._buf.clear()

    @property
    def filled(self) -> bool:
        return len(self._buf) >= self.window_size


class StableJudge:
    """稳定判定：连续 N 次采样变化 < 阈值才确认稳定值。

    用法:
        judge = StableJudge(thresh=0.5, count_required=3)
        for sample in stream:
            is_stable, stable_value = judge.update(sample)
            if is_stable:
                display(stable_value)
    """

    def __init__(self, thresh: float = 0.5, count_required: int = 3) -> None:
        if count_required < 1:
            raise ValueError("count_required 必须 >= 1")
        self.thresh = float(thresh)
        self.count_required = int(count_required)
        self._stable_value: float = 0.0
        self._consecutive: int = 0

    def update(self, value: float) -> Tuple[bool, float]:
        """返回 (是否稳定, 当前显示值)。"""
        v = float(value)
        if self._consecutive == 0:
            self._stable_value = v
            self._consecutive = 1
            return False, v

        if abs(v - self._stable_value) <= self.thresh:
            # 在阈值内，累计
            self._consecutive += 1
            # 用更接近当前趋势的值更新（轻微平滑）
            self._stable_value = (self._stable_value * (self._consecutive - 1) + v) / self._consecutive
        else:
            # 跳变，重置
            self._stable_value = v
            self._consecutive = 1
            return False, v

        if self._consecutive >= self.count_required:
            return True, self._stable_value
        return False, self._stable_value

    def reset(self) -> None:
        self._stable_value = 0.0
        self._consecutive = 0
