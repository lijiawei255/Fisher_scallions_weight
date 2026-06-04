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
        """统一流程：停止自动发送 → 排空 → 执行动作 → 等待 → 多重排空 → 重启。

        关键：硬件执行去皮/取消去皮需要约 600ms 去抖采集。在此期间及之前
        产生的旧帧会残留在串口缓冲区，必须在重启自动发送后彻底丢弃。
        """
        if not self.driver.is_open:
            return False
        try:
            # 1) 发一个无关指令终止自动发送（手册第 12 条：模块收到其他任意有效指令后自动发送将失效）
            self.driver.send_command(build_read_weight_cmd(self.driver.address))
            time.sleep(0.1)

            # 2) 排空：丢弃停止自动发送期间可能残留的帧
            self.driver.flush_buffers()

            # 3) 执行动作（去皮/取消去皮）
            action()

            # 4) 等待模块去抖采集（手册：约 600ms）
            time.sleep(wait_after)

            # 5) 排空：丢弃动作期间产生的旧帧
            self.driver.flush_buffers()

            # 6) 短暂等待，让传输中的字节到达主机
            time.sleep(0.1)

            # 7) 再次排空：捕获步骤 5-6 之间到达的残留字节
            self.driver.flush_buffers()

            # 8) 重新启动自动发送（发两次确保生效）
            self.driver.start_auto_send(mode=1)
            time.sleep(0.05)
            self.driver.start_auto_send(mode=1)

            # 9) 最终排空：丢弃自动发送命令本身的响应帧
            self.driver.flush_buffers()

            return True
        except Exception:
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
