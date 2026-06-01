"""
集中管理所有可调常量。

适配 CMCU-07 称重变送器 (TTL 自定义协议 V3.70) 1kg 量程。
"""
from __future__ import annotations

# ============= 串口参数 =============
SERIAL_BAUDRATE = 9600          # 新电子秤默认波特率
SERIAL_TIMEOUT = 0.2            # 串口读取超时（秒）
UI_UPDATE_INTERVAL = 100        # 界面刷新周期（ms），与自动发送 100ms 对齐
MODULE_ADDRESS = 0              # 变送器模块地址（默认 0）

# ============= 校准参数 =============
# 默认假设电子秤已通过专用调试软件完成硬件级设置（波特率、零点、砝码校准等一次性操作）
# 本程序只做会话级操作：每次连接后自动去皮
CAL_RESOLUTION_G = 0.1          # 1 个刻度代表的实际重量（出厂默认 0.1g 分辨率）
CAL_WEIGHT_TICKS = 5000         # 砝码校准参考值（500g 砝码 / 0.1g = 5000）— 仅作参考
GRAMS_PER_TICK = CAL_RESOLUTION_G  # 0.1 g/tick

# 启动时自动去皮
AUTO_TARE_ON_CONNECT = True        # 连接成功后自动去皮（每次运行都会执行）
AUTO_TARE_COUNTDOWN_SECONDS = 3    # 倒计时秒数（可手动取消）
CALIBRATION_WAIT_SECONDS = 0.8     # 校准指令后等待模块去抖采集的秒数

# ============= 称重业务参数 =============
WEIGHT_THRESH_HIGH = 5.0        # 推板启动阈值（g）
WEIGHT_THRESH_LOW  = 3.0        # 推板停止阈值（g）
MAX_TOTAL_GRAMS   = 9999.0      # 总重显示上限（g）
FILTER_WINDOW_SIZE = 5          # 滑动滤波窗口（从 1 提升到 5，抗抖）
STABLE_THRESH_GRAMS = 0.5       # 稳定判定阈值
STABLE_COUNT_REQUIRED = 3       # 连续 N 次落入阈值才确认稳定
ENTER_WEIGHING_STREAK = 2       # 连续 N 次 > 高阈值才进入 WEIGHING（防误触发）
EXIT_WEIGHING_STREAK = 2        # 连续 N 次 < 低阈值才退出 WEIGHING

# ============= 模拟模式（虚拟测试） =============
SIMULATE_MODE_DEFAULT = False   # True 启动时进入虚拟测试模式（无需电子秤）
SIM_PATTERN = "basic"           # "basic"=0/30g 循环
SIM_NOISE_GRAMS = 0.0           # 模拟噪声幅度（开发滤波算法用）

# ============= UI =============
WINDOW_TITLE = "葱称重系统 - 北京交通大学"
BG_COLOR = '#f0f8f0'
TOTAL_MAX = MAX_TOTAL_GRAMS     # 兼容旧字段
