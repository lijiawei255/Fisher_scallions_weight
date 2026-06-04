"""
串口驱动层：封装 pyserial。

- ScaleDriver: 真实硬件，通过 pyserial 收发。
- SimulatedScaleDriver: 虚拟测试，不打开串口，按周期生成 0/30g 帧。

两者实现同一组方法（open/close/is_open/send_command/read_frames/start_auto_send），
UI 层无差别使用。
"""
from __future__ import annotations

import math
import time
from typing import Optional

try:
    import serial  # type: ignore
    import serial.tools.list_ports  # type: ignore
except ImportError:  # 允许无硬件环境开发
    serial = None  # type: ignore
    serial_tools = None  # type: ignore

import config
from scale_protocol import (
    FrameParser,
    build_start_auto_send_cmd,
    build_zero_calibration_cmd,
    build_tare_cmd,
    build_untare_cmd,
    build_weight_calibration_cmd,
    START_BYTE,
    END_BYTE,
    CMD_READ_WEIGHT,
)


# ============= 自定义异常 =============
class ScaleConnectionError(RuntimeError):
    pass


# ============= 真实驱动 =============
class ScaleDriver:
    """真实串口驱动。"""

    def __init__(self, port: str, baud: int = config.SERIAL_BAUDRATE,
                 timeout: float = config.SERIAL_TIMEOUT,
                 address: int = config.MODULE_ADDRESS) -> None:
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self.address = address
        self._ser: Optional["serial.Serial"] = None
        self._parser = FrameParser()

    # ---- 生命周期 ----
    def open(self) -> None:
        if serial is None:
            raise ScaleConnectionError("pyserial 未安装，无法连接真实电子秤")
        if self._ser is not None and self._ser.is_open:
            return
        try:
            self._ser = serial.Serial(
                port=self.port,
                baudrate=self.baud,
                timeout=self.timeout,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
            )
        except Exception as e:
            raise ScaleConnectionError(f"无法打开串口 {self.port}: {e}") from e
        # 清空残留
        try:
            self._ser.reset_input_buffer()
            self._ser.reset_output_buffer()
        except Exception:
            pass

    def close(self) -> None:
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None
        self._parser.reset()

    @property
    def is_open(self) -> bool:
        return self._ser is not None and self._ser.is_open

    # ---- I/O ----
    def send_command(self, cmd: bytes) -> None:
        if not self.is_open:
            raise ScaleConnectionError("串口未打开")
        try:
            self._ser.write(cmd)
            self._ser.flush()
        except Exception as e:
            raise ScaleConnectionError(f"串口写入失败: {e}") from e

    def read_frames(self) -> list[dict]:
        """读取缓冲区中所有有效帧（处理粘包/多帧到达）。"""
        if not self.is_open:
            return []
        try:
            waiting = self._ser.in_waiting
        except Exception as e:
            raise ScaleConnectionError(f"串口状态查询失败: {e}") from e
        if waiting <= 0:
            return []
        try:
            data = self._ser.read(waiting)
        except Exception as e:
            raise ScaleConnectionError(f"串口读取失败: {e}") from e
        return list(self._parser.feed(data))

    def flush_buffers(self) -> None:
        """清空串口输入缓冲区和帧解析器（去皮/取消去皮后使用，丢弃旧帧）。"""
        if self._ser is not None and self._ser.is_open:
            try:
                self._ser.reset_input_buffer()
            except Exception:
                pass
        self._parser.reset()

    # ---- 模式 ----
    def start_auto_send(self, mode: int = 1) -> None:
        """启动自动发送模式（手册第 12 条）。"""
        cmd = build_start_auto_send_cmd(self.address, mode=mode)
        self.send_command(cmd)

    # ---- 校准方法（封装在驱动层方便调用） ----
    def zero_calibrate(self) -> None:
        self.send_command(build_zero_calibration_cmd(self.address))

    def tare(self) -> None:
        self.send_command(build_tare_cmd(self.address))

    def untare(self) -> None:
        self.send_command(build_untare_cmd(self.address))

    def weight_calibrate(self, weight_ticks: int) -> None:
        self.send_command(build_weight_calibration_cmd(weight_ticks, self.address))


# ============= 模拟驱动 =============
class SimulatedScaleDriver:
    """虚拟测试驱动：按 0/30g 周期生成符合协议的 10 字节帧。"""

    def __init__(self, pattern: str = config.SIM_PATTERN,
                 noise: float = config.SIM_NOISE_GRAMS,
                 address: int = config.MODULE_ADDRESS) -> None:
        self.address = address
        self.pattern = pattern
        self.noise = noise
        self._open = True
        self._start = time.time()
        self._parser = FrameParser()

    def open(self) -> None:
        self._open = True
        self._start = time.time()
        self._parser.reset()

    def close(self) -> None:
        self._open = False
        self._parser.reset()

    @property
    def is_open(self) -> bool:
        return self._open

    def _current_grams(self) -> float:
        elapsed = time.time() - self._start
        cycle = elapsed % 16.0
        if cycle < 4.0:
            base = 0.0
        elif cycle < 10.0:
            base = 30.0
        else:
            base = 0.0
        if self.noise > 0:
            base += math.sin(elapsed * 3.0) * self.noise
        return max(0.0, base)

    def _build_frame(self, grams: float) -> bytes:
        ticks = int(round(grams / config.GRAMS_PER_TICK))
        hi = (ticks >> 16) & 0xFF
        mid = (ticks >> 8) & 0xFF
        lo = ticks & 0xFF
        sign = 0
        # 帧布局: [0xAA][CMD][ADDR][SIGN][HI][MID][LO][CHK_H][CHK_L][0xFF]
        # 校验 = sum(buf[1:7]) → (buf[7] << 8) | buf[8]
        buf = bytearray([START_BYTE, CMD_READ_WEIGHT, self.address, sign, hi, mid, lo, 0, 0, END_BYTE])
        chk = sum(buf[1:7]) & 0xFFFF
        buf[7] = (chk >> 8) & 0xFF
        buf[8] = chk & 0xFF
        return bytes(buf)

    def send_command(self, cmd: bytes) -> None:
        # 模拟器忽略指令，但保留接口兼容
        return

    def read_frames(self) -> list[dict]:
        if not self._open:
            return []
        # 节流：每 ~100ms 返回一帧
        now = time.time()
        if not hasattr(self, "_last_emit") or now - self._last_emit >= 0.1:
            self._last_emit = now
            frame_bytes = self._build_frame(self._current_grams())
            return list(self._parser.feed(frame_bytes))
        return []

    def start_auto_send(self, mode: int = 1) -> None:
        return

    def flush_buffers(self) -> None:
        """模拟器无缓冲区，仅重置帧解析器以保持接口兼容。"""
        self._parser.reset()

    def zero_calibrate(self) -> None:
        # 模拟器中"校准"等价于把基线归零
        self._start = time.time()

    def tare(self) -> None:
        self.zero_calibrate()

    def untare(self) -> None:
        self.zero_calibrate()

    def weight_calibrate(self, weight_ticks: int) -> None:
        # 模拟器中"砝码校准"直接生效：调整单位换算系数
        if weight_ticks > 0:
            config.GRAMS_PER_TICK = 500.0 / weight_ticks  # 假设用 500g 砝码


# ============= 工具函数 =============
def list_serial_ports() -> list[str]:
    """枚举可用串口。"""
    if serial is None:
        return []
    return [p.device for p in serial.tools.list_ports.comports()]


