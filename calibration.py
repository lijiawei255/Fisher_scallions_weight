"""
会话级操作管理：去皮 / 取消去皮。

设计说明：
- 硬件级一次性设置（波特率、零点校准、砝码校准等）由专用调试软件完成
  （见 README "新电子秤初始设置" 一节）。本程序不提供这些功能。
- 本程序只做每次运行都会做的"会话级"操作：去皮（把当前重量视为零临时基准）。
  去皮是临时清零（断电丢失），不会改变电子秤的硬件校准参数。
"""
from __future__ import annotations

import time
from typing import Callable

import config
from scale_driver import ScaleDriver, ScaleConnectionError
from scale_protocol import build_read_weight_cmd


class Calibrator:
    """对 ScaleDriver 的会话级操作（去皮/取消去皮）做高层封装。"""

    def __init__(self, driver: ScaleDriver) -> None:
        self.driver = driver

    def _do_with_restart(self, action: Callable[[], None], wait_after: float) -> bool:
        """统一流程：停止自动发送 → 执行动作 → 等待去抖 → 重新启动自动发送。"""
        if not self.driver.is_open:
            return False
        try:
            # 1) 发一个无关指令终止自动发送（手册第 12 条：模块收到其他任意有效指令后自动发送将失效）
            self.driver.send_command(build_read_weight_cmd(self.driver.address))
            time.sleep(0.05)
            # 2) 执行动作
            action()
            # 3) 等待模块去抖
            time.sleep(wait_after)
            # 4) 重新启动自动发送
            self.driver.start_auto_send(mode=1)
            return True
        except (ScaleConnectionError, Exception):
            return False

    def tare(self) -> bool:
        """第 4 条指令：去皮置零（把当前重量临时设为 0，断电丢失）。"""
        return self._do_with_restart(
            self.driver.tare,
            wait_after=config.CALIBRATION_WAIT_SECONDS,
        )

    def untare(self) -> bool:
        """第 5 条指令：取消去皮（恢复去皮前基准）。"""
        return self._do_with_restart(
            self.driver.untare,
            wait_after=config.CALIBRATION_WAIT_SECONDS,
        )
