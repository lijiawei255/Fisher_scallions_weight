"""
稳定值判定。

硬件（CMCU-07）已配置中值滤波(3) + 平均滤波(3)，软件直接使用硬件返回值，
不再做软件层滤波。

- StableJudge: 连续 N 次变化 < 阈值才确认稳定，避免数字跳变。
"""
from __future__ import annotations

from typing import Tuple


class StableJudge:
    """稳定判定：连续 N 次采样变化 < 阈值才确认稳定值。

    设计目的：避免 UI 显示重量爬升/下降过程中的中间值。
    例如放上 30g 物品时，原始读数从 0 爬到 30，跳变前的中间值（5, 10, 15…）
    都不应被显示；同理物品离开时也不应逐级下降。

    用法:
        judge = StableJudge(thresh=0.5, count_required=3)
        for sample in stream:
            is_stable, stable_value = judge.update(sample)
            # 即使未稳定，也总是返回"当前确认的稳定值"——它在跳变时不变
            display(stable_value)

    行为约定:
        - 跳变时：保持旧稳定值不变（不暴露跳变中间值）
        - 新值需连续 N 次落在阈值内才被确认为新稳定值
    """

    def __init__(self, thresh: float = 0.5, count_required: int = 3) -> None:
        if count_required < 1:
            raise ValueError("count_required 必须 >= 1")
        self.thresh = float(thresh)
        self.count_required = int(count_required)
        self._stable_value: float = 0.0        # 当前已确认的稳定值（对外可见）
        self._pending_value: float = 0.0        # 候选值（跳变后开始累积）
        self._consecutive: int = 0              # 候选值连续命中次数

    def update(self, value: float) -> Tuple[bool, float]:
        """返回 (是否刚确认稳定, 当前稳定值)。

        行为约定:
        - 跳变时（与 _stable_value 差 > 阈值）：保持 _stable_value 不变，
          把 _pending_value 设为新值，_consecutive 重新计数
        - 后续若新值与 _pending_value 一致（都在新值附近），继续累加
        - 累加到 N 次：把 _stable_value 平滑到新值（视为已稳定）
        - 累加过程中若新值再次跳变（既不接近 _stable_value 也不接近 _pending_value），
          仍保持 _stable_value，把 _pending_value 重置
        """
        v = float(value)
        if self._consecutive == 0:
            # 首次/重置后：初始化候选值，但不更新 _stable_value
            self._pending_value = v
            self._consecutive = 1
            return False, self._stable_value

        # 已在跳变中累积：看新值是否仍在 _pending_value 阈值内
        if abs(v - self._pending_value) <= self.thresh:
            # 候选值附近 → 累加
            self._consecutive += 1
            self._pending_value = (self._pending_value * (self._consecutive - 1) + v) / self._consecutive
            if self._consecutive >= self.count_required:
                # 连续 N 次落在新候选值附近：把 _stable_value 切到新值
                self._stable_value = self._pending_value
                return True, self._stable_value
            return False, self._stable_value
        else:
            # 又一次跳变（既不接近 _stable_value 也不接近 _pending_value）
            # 或不接近 _pending_value 但接近 _stable_value
            # 这里统一处理：把 _pending_value 重置为新值，_stable_value 不变
            self._pending_value = v
            self._consecutive = 1
            return False, self._stable_value

    def force_set(self, value: float) -> None:
        """强制覆盖稳定值（用于去皮后立即清零、或状态机判定物品离开后强制重置）。

        调用后 _stable_value 立刻变为 value，且后续的微小抖动不会改变它
        （因为新值在 _stable_value 阈值内，但不会达到连续 N 次的累积——因为
        _consecutive 被重置为 1，后续每次抖动都会与"刚稳定的 _stable_value"
        比较，需要重新连续 N 次才会再次更新）。
        """
        self._stable_value = float(value)
        self._pending_value = float(value)
        self._consecutive = 1  # 视为"刚开始"累积，下次 update 起算

    def reset(self) -> None:
        self._stable_value = 0.0
        self._pending_value = 0.0
        self._consecutive = 0
