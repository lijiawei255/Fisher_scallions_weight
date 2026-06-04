"""
集中管理所有可调常量。

适配 CMCU-07 称重变送器 (TTL 自定义协议 V3.70) 1kg 量程。
"""

from __future__ import annotations

# ============= 串口参数 =============
SERIAL_BAUDRATE = 9600  # 新电子秤默认波特率
SERIAL_TIMEOUT = 0.2  # 串口读取超时（秒）
UI_UPDATE_INTERVAL = 100  # 界面刷新周期（ms），与自动发送 100ms 对齐
MODULE_ADDRESS = 0  # 变送器模块地址（默认 0）

# ============= 校准参数 =============
# 默认假设电子秤已通过专用调试软件完成硬件级设置（波特率、零点、砝码校准等一次性操作）
# 本程序只做会话级操作：每次连接后自动去皮
CAL_RESOLUTION_G = 1.0  # 1 个刻度代表的实际重量（500g 砝码输入 500 → 1g/刻度）
CAL_WEIGHT_TICKS = 500  # 砝码校准参考值（500g 砝码 / 1g = 500）— 仅作参考
GRAMS_PER_TICK = CAL_RESOLUTION_G  # 1.0 g/tick

# 启动时自动去皮
AUTO_TARE_ON_CONNECT = True  # 连接成功后自动去皮（每次运行都会执行）
AUTO_TARE_COUNTDOWN_SECONDS = 3  # 倒计时秒数（可手动取消）
CALIBRATION_WAIT_SECONDS = 0.8  # 校准指令后等待模块去抖采集的秒数

# ============= 称重业务参数 =============
WEIGHT_THRESH_HIGH = 2.0  # 进入 WEIGHING 阈值（g）
WEIGHT_THRESH_LOW = 2.0  # 退出 WEIGHING 阈值（g）
MAX_TOTAL_GRAMS = 9999.0  # 总重显示上限（g）
STABLE_THRESH_GRAMS = 1.0  # 稳定判定阈值（1g 分辨率下允许 ±1g 波动）
STABLE_COUNT_REQUIRED = 1  # 硬件已滤波(中值3+平均3)，单次输出可信，加快响应和锁定速度
ENTER_WEIGHING_STREAK = 2  # 连续 N 次 > 高阈值才进入 WEIGHING（防误触发）
EXIT_WEIGHING_STREAK = 1  # 连续 N 次 < 低阈值才退出 WEIGHING（硬件已滤波，单次可信）

# ============= 模拟模式（虚拟测试） =============
SIMULATE_MODE_DEFAULT = False  # True 启动时进入虚拟测试模式（无需电子秤）
SIM_PATTERN = "basic"  # "basic"=0/30g 循环
SIM_NOISE_GRAMS = 0.0  # 模拟噪声幅度（开发滤波算法用）

# ============= UI =============
WINDOW_TITLE = "葱称重系统 - 北京交通大学"
BG_COLOR = "#f0f8f0"

# ============= 主题色（design tokens）=============
# 现代化企业 SaaS 卡片风：浅色 + 阴影 + 圆角 + 柔和
THEME = {
    # 背景
    "bg": "#f4f6fa",  # 主背景（极浅冷灰）
    "card_bg": "#ffffff",  # 卡片背景
    "card_border": "#e2e8f0",  # 卡片描边
    "panel_bg": "#eef2f7",  # 底栏操作区
    "topbar_bg": "#ffffff",  # 顶栏
    # 主题色
    "primary": "#16a34a",  # 主绿
    "primary_dark": "#15803d",
    "primary_light": "#dcfce7",
    "accent": "#0ea5e9",  # 蓝色点缀
    "accent_dark": "#0369a1",
    "accent_light": "#e0f2fe",
    # 状态色
    "success": "#16a34a",
    "warning": "#d97706",
    "warning_light": "#fef3c7",
    "danger": "#dc2626",
    "danger_light": "#fee2e2",
    "muted": "#94a3b8",
    "muted_dark": "#64748b",
    "text": "#0f172a",
    "text_dim": "#475569",
    # 尺寸
    "radius": 16,
    "card_pad": 24,
    "shadow_color": "#0f172a",  # 用于绘制阴影
    # 字体
    "font_zh": "Microsoft YaHei",  # 数字/英文
    "font_cn": "FangSong",  # 中文标题
}

# ============= 连接监控 =============
CONNECTION_TIMEOUT_SECONDS = 5.0  # 超过此时间未收到数据，视为断开

# ============= 瞬时错误容忍 =============
TRANSIENT_ERROR_THRESHOLD = 3  # 连续 N 次读取失败才判定断开（容忍偶发 USB 抖动）

# ============= 自动重连 =============
RECONNECT_MAX_RETRIES = 30  # 最大重连尝试次数（约 30×2s = 60s）
RECONNECT_INTERVAL_MS = 2000  # 重连尝试间隔（毫秒）
RECONNECT_REFRESH_PORTS = True  # 重连时自动刷新端口列表
