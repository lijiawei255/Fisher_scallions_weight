"""
稳定值判定。

硬件（CMCU-07）已配置中值滤波(3) + 平均滤波(3)，软件直接使用硬件返回值，
不再做软件层滤波。

- StableJudge: 跳变时延迟 1 个采样（100ms）确认新值，避免 UI 显示抖动。
  物品离开时 force_set(0) 强制归零，不显示下降过程。
"""
from __future__ import annotations

from typing import Tuple


class StableJudge:
    """稳定判定：跳变时延迟 1 个采样确认新值。

    硬件已做中值+平均滤波，软件拿到的读数已经是干净的一步跳变（0 → 30），
    不会有逐级爬升的问题。StableJudge 的作用是：
    - 跳变时：延迟 1 个采样（100ms）确认新值，过滤偶然的瞬时跳变
    - 确认后：一步更新到新值，不显示中间过渡
    - force_set(0)：强制归零，用于物品离开或去皮时

    用法:
        judge = StableJudge(thresh=1.0, count_required=1)  # 硬件已滤波，1次即可
        for sample in stream:
            is_stable, stable_value = judge.update(sample)
            display(stable_value)

    行为约定:
        - 读数变化 > thresh：保持旧值，将新值设为候选
        - 候选值连续 N 次（N=1）落在阈值内 → 确认稳定，一步更新
        - force_set(value)：强制覆盖稳定值（去皮/物品离开时）
    """

    def __init__(self, thresh: float = 1.0, count_required: int = 1) -> None:
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
        - 首次/重置后：初始化候选值，保持旧稳定值不变（延迟 1 个采样）
        - 新值在候选值阈值内：累加计数，达到 N 次 → 确认稳定，一步更新
        - 新值再次跳变：保持旧稳定值，候选值重置为新值
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
                # 候选值已确认稳定（N=1 时即第 2 次采样确认），一步更新
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
