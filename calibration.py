"""
校准管理：封装零点校准、砝码校准、去皮置零的高级流程。

设计要点（参照手册 V3.70 第 5.3 节）:
- 校准指令后模块需约 600ms 去抖采集，期间不应再发其他指令
- 校准前应停止自动发送模式（发送任意其他有效指令即可终止，参见第 12 条）
- 校准完成后重新启动自动发送
"""
from __future__ import annotations

import time
from typing import Callable

import config
from scale_driver import ScaleDriver, ScaleConnectionError
from scale_protocol import build_read_weight_cmd


class Calibrator:
    """对 ScaleDriver 的校准操作做高层封装。"""

    def __init__(self, driver: ScaleDriver) -> None:
        self.driver = driver

    def _do_calibration(self, send_fn: Callable[[], None], wait_after: float) -> bool:
        """统一校准流程：停止自动发送 → 发指令 → 等待去抖 → 重新启动自动发送。"""
        if not self.driver.is_open:
            return False
        try:
            # 1) 发一个无关指令终止自动发送（手册第 12 条：模块收到其他任意有效指令后自动发送将失效）
            self.driver.send_command(build_read_weight_cmd(self.driver.address))
            time.sleep(0.05)
            # 2) 发校准指令
            send_fn()
            # 3) 等待模块去抖
            time.sleep(wait_after)
            # 4) 重新启动自动发送
            self.driver.start_auto_send(mode=1)
            return True
        except (ScaleConnectionError, Exception):
            return False

    def zero_calibrate(self) -> bool:
        """第 3 条指令：零点校准。"""
        return self._do_calibration(
            self.driver.zero_calibrate,
            wait_after=config.CALIBRATION_WAIT_SECONDS,
        )

    def weight_calibrate(self, weight_ticks: int) -> bool:
        """第 6 条指令：砝码校准。weight_ticks = 砝码g / 分辨率g。"""
        return self._do_calibration(
            lambda: self.driver.weight_calibrate(weight_ticks),
            wait_after=config.CALIBRATION_WAIT_SECONDS,
        )

    def tare(self) -> bool:
        """第 4 条指令：去皮置零。"""
        if not self.driver.is_open:
            return False
        try:
            self.driver.send_command(build_read_weight_cmd(self.driver.address))
            time.sleep(0.05)
            self.driver.tare()
            time.sleep(config.CALIBRATION_WAIT_SECONDS)
            self.driver.start_auto_send(mode=1)
            return True
        except Exception:
            return False

    def untare(self) -> bool:
        """第 5 条指令：取消去皮。"""
        if not self.driver.is_open:
            return False
        try:
            self.driver.send_command(build_read_weight_cmd(self.driver.address))
            time.sleep(0.05)
            self.driver.untare()
            time.sleep(config.CALIBRATION_WAIT_SECONDS)
            self.driver.start_auto_send(mode=1)
            return True
        except Exception:
            return False
