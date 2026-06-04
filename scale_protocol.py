"""
协议层：CMCUC-07 TTL 自定义协议 V3.70

- 帧格式 10 字节：0xAA CMD ADDR SIGN HIGH MID LOW CHK_H CHK_L 0xFF
- 校验：(Byte2+...+Byte7) == (Byte8*256+Byte9)
- 文档：电子秤资料/.../电子秤串口模块说明书 V3.70___20240308-已解锁.pdf

本模块不依赖 pyserial，纯函数 + 常量，便于单元测试。
"""
from __future__ import annotations

from typing import Iterator, Optional

# ============= 帧常量 =============
START_BYTE = 0xAA
END_BYTE = 0xFF
FRAME_LENGTH = 10

# ============= 指令首字节 =============
CMD_READ_AD         = 0xA1   # 第 1 条：直接测 AD 值
CMD_READ_WEIGHT     = 0xA3   # 第 2 条：读重量（最常用）
CMD_ZERO_CALIBRATE  = 0xAA   # 第 3 条：零点校准
CMD_TARE            = 0xAB   # 第 4 条：去皮置零（临时清零）
CMD_UNTARE          = 0xAC   # 第 5 条：取消去皮
CMD_WEIGHT_CALIB    = 0xAD   # 第 6 条：砝码校准
CMD_WRITE_FILTERS   = 0xFA   # 第 7 条：同时写地址+滤波（广播）
CMD_QUERY_INFO      = 0xF1   # 第 8 条：查询模块信息
CMD_WRITE_PARAMS    = 0xFB   # 第 9 条：修改多参数
CMD_QUERY_PARAMS    = 0xF2   # 第 10 条：查询参数
CMD_RESET           = 0x51   # 第 11 条：恢复出厂
CMD_AUTO_SEND       = 0xA4   # 第 12 条：启动自动发送

# ============= 工具函数 =============
def xor_checksum(bs: bytes) -> int:
    """异或校验（手册第 1 条指令：E=A^B^C^D）。"""
    c = 0
    for b in bs:
        c ^= b
    return c & 0xFF


def _build_cmd(first: int, addr: int, extra: bytes = b"") -> bytes:
    """通用 5 字节指令构造：[CMD] [ADDR] [extra...] [xor]"""
    head = bytes([first & 0xFF, addr & 0xFF]) + extra
    chk = xor_checksum(head)
    return head + bytes([chk])


# ============= 指令构造 =============
def build_read_weight_cmd(addr: int = 0) -> bytes:
    """第 2 条指令：读重量数据。"""
    return _build_cmd(CMD_READ_WEIGHT, addr, bytes([0xA2, 0xA4]))


def build_start_auto_send_cmd(addr: int = 0, mode: int = 1) -> bytes:
    """第 12 条指令：启动自动发送模式。
    mode=1: 100ms 间隔；mode=2: 变化时发送。
    """
    if mode == 1:
        return _build_cmd(CMD_AUTO_SEND, addr, bytes([0xA3, 0xA5]))
    else:
        return _build_cmd(CMD_AUTO_SEND, addr, bytes([0xA5, 0xA3]))


def build_zero_calibration_cmd(addr: int = 0) -> bytes:
    """第 3 条指令：零点校准（取当前 AD 永久保存为零点）。"""
    return _build_cmd(CMD_ZERO_CALIBRATE, addr, bytes([0xA9, 0xAB]))


def build_tare_cmd(addr: int = 0) -> bytes:
    """第 4 条指令：去皮置零（临时清零，断电丢失）。"""
    return _build_cmd(CMD_TARE, addr, bytes([0xAA, 0xAC]))


def build_untare_cmd(addr: int = 0) -> bytes:
    """第 5 条指令：取消去皮。"""
    return _build_cmd(CMD_UNTARE, addr, bytes([0xAB, 0xAD]))


def build_weight_calibration_cmd(weight_ticks: int, addr: int = 0) -> bytes:
    """第 6 条指令：砝码校准。
    weight_ticks: 砝码值除以分辨率。例如 500g 砝码 0.1g 分辨率 → 5000。
    """
    if not (0 <= weight_ticks <= 0xFFFF):
        raise ValueError(f"weight_ticks 超出 16 位范围: {weight_ticks}")
    hi = (weight_ticks >> 8) & 0xFF
    lo = weight_ticks & 0xFF
    return _build_cmd(CMD_WEIGHT_CALIB, addr, bytes([hi, lo]))


# ============= 帧解析 =============
def parse_frame(buf: bytes) -> Optional[dict]:
    """从 10 字节缓冲解析一帧。校验失败返回 None。

    返回结构:
        {
            "cmd": int,           # 命令字节
            "addr": int,          # 模块地址
            "sign": int,          # 0=正 1=负（仅 A3 读重量有意义）
            "weight_ticks": int,  # 24 位无符号整数
            "raw": bytes,         # 原始 10 字节
        }
    """
    if len(buf) < FRAME_LENGTH:
        return None
    if buf[0] != START_BYTE or buf[FRAME_LENGTH - 1] != END_BYTE:
        return None

    # 累加和校验（手册：Byte2..Byte7 之和 == Byte8*256 + Byte9；1-indexed）
    # 0-indexed: sum(buf[1:7]) == (buf[7] << 8) | buf[8]
    chk = sum(buf[1:7]) & 0xFFFF
    expected = (buf[7] << 8) | buf[8]
    if chk != expected:
        return None

    cmd = buf[1]
    addr = buf[2]
    sign = buf[3]
    weight_ticks = (buf[4] << 16) | (buf[5] << 8) | buf[6]
    return {
        "cmd": cmd,
        "addr": addr,
        "sign": sign,
        "weight_ticks": weight_ticks,
        "raw": bytes(buf[:FRAME_LENGTH]),
    }


# ============= 滑动窗口解析器（处理跨包/粘包） =============
class FrameParser:
    """累积字节流，按 0xAA…0xFF 边界切分并校验。

    用法:
        p = FrameParser()
        for frame in p.feed(serial_bytes):
            print(frame)
    """

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> Iterator[dict]:
        if not data:
            return
        self._buf.extend(data)
        while True:
            frame = self._try_extract_one()
            if frame is None:
                break
            yield frame

    def _try_extract_one(self) -> Optional[dict]:
        # 找到下一个 START_BYTE
        if not self._buf:
            return None
        while True:
            start_idx = -1
            for i, b in enumerate(self._buf):
                if b == START_BYTE:
                    start_idx = i
                    break
            if start_idx < 0:
                # 没有 START_BYTE，全部丢弃
                self._buf.clear()
                return None
            if start_idx > 0:
                del self._buf[:start_idx]
            # 等待足够字节
            if len(self._buf) < FRAME_LENGTH:
                return None
            # 找 END_BYTE
            if self._buf[FRAME_LENGTH - 1] != END_BYTE:
                # 当前位置不是有效帧边界，丢弃 START 字节继续找下一个
                del self._buf[0]
                continue
            frame = parse_frame(bytes(self._buf[:FRAME_LENGTH]))
            del self._buf[:FRAME_LENGTH]
            if frame is None:
                # 校验失败，跳到下一个 START 继续
                continue
            return frame

    def reset(self) -> None:
        self._buf.clear()


# ============= 单位换算 =============
def weight_ticks_to_grams(ticks: int, sign: int, grams_per_tick: float = 0.1) -> float:
    """将刻度转换为实际 g。"""
    value = ticks * grams_per_tick
    if sign == 1:
        value = -value
    return round(value, 3)
