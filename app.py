"""
大葱称重系统 UI（Tkinter）— Apple 风格重设计版。

适配 1kg 量程 HX711 TTL 变送器电子秤（CMCU-07 协议 V3.70）。

硬件已配置中值滤波(3) + 平均滤波(3)，软件直接使用返回值，不再做软件层滤波。
数据管道：硬件输出 → 稳定判定 → 显示

主要功能:
- 实时重量显示（g，整数）— 稳定后才显示，不显示爬升/下降中间值
- 累计总重 + 清零
- 串口连接管理（自动发送模式）
- 连接后自动去皮（3 秒可取消倒计时）
- 运行时去皮 / 取消去皮
- 虚拟测试模式（无需电子秤）
"""
from __future__ import annotations

import math
import os
import random
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

import config
from calibration import Calibrator
from scale_driver import (
    ScaleConnectionError,
    ScaleDriver,
    SimulatedScaleDriver,
    list_serial_ports,
)
from scale_protocol import weight_ticks_to_grams
from smooth_number import SmoothNumberAnimator
from weight_filter import StableJudge
from weight_state import WeightAccumulator


# ==================== Apple 风格设计令牌 ====================
_BG = "#f0fdf4"              # 极浅薄荷绿背景
_CARD_BG = "#ffffff"          # 卡片纯白
_CARD_BORDER = "#e2e8f0"      # 卡片细边框
_PRIMARY = "#059669"          # 祖母绿（稳定）
_PRIMARY_LIGHT = "#34d399"    # 浅亮绿（活跃/高亮）
_PRIMARY_DARK = "#047857"      # 深绿（悬停/按下）
_TEXT = "#1e293b"             # 主文字深灰
_TEXT_DIM = "#64748b"         # 次要文字灰
_DANGER = "#dc2626"           # 危险红
_DANGER_HOVER = "#ef4444"     # 危险红悬停
_DANGER_DARK = "#b91c1c"      # 危险红按下


# ==================== 资源路径（PyInstaller 兼容）====================
def resource_path(relative: str) -> str:
    """获取资源绝对路径。PyInstaller 单文件模式下，资源被解压到 sys._MEIPASS。

    开发环境（直接 python main.py）：返回当前工作目录下的文件
    打包后（运行 exe）：返回 PyInstaller 解压临时目录下的文件
    """
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


# ==================== 动态背景粒子（气泡风格）====================
class BubbleParticle:
    """缓慢上升的气泡粒子，带有轻微左右摇摆，支持颜色切换。"""

    IDLE_COLORS = ['#dcfce7', '#d1fae5', '#a7f3d0']
    ACTIVE_COLORS = ['#86efac', '#4ade80', '#22c55e', '#16a34a']

    def __init__(self, canvas: tk.Canvas, width: int, height: int) -> None:
        self.canvas = canvas
        self.width = width
        self.height = height
        self.radius = random.randint(2, 5)
        self.speed = random.uniform(0.3, 0.8)
        self.sway_amp = random.uniform(0.5, 2.0)
        self.sway_freq = random.uniform(0.01, 0.03)
        self.phase = random.uniform(0, 2 * 3.14159)
        self._reset()

    def _reset(self) -> None:
        self.x = random.randint(0, self.width)
        self.y = self.height + random.randint(10, 100)
        self.color = random.choice(self.IDLE_COLORS)
        self.id = self.canvas.create_oval(
            self.x - self.radius, self.y - self.radius,
            self.x + self.radius, self.y + self.radius,
            fill=self.color, outline="",
        )

    def move(self) -> None:
        self.y -= self.speed
        self.phase += self.sway_freq
        self.x += math.sin(self.phase) * self.sway_amp

        if self.y < -self.radius * 2:
            self._reset()
            return

        self.canvas.coords(
            self.id,
            self.x - self.radius, self.y - self.radius,
            self.x + self.radius, self.y + self.radius,
        )

    def set_active(self, active: bool = True) -> None:
        """切换粒子颜色（空闲/活跃）。"""
        palette = self.ACTIVE_COLORS if active else self.IDLE_COLORS
        self.color = random.choice(palette)
        self.canvas.itemconfig(self.id, fill=self.color)


# ==================== Toast 通知 ====================
class ToastManager:
    """管理 Toast 通知，从屏幕顶部滑入，自动消失。"""

    def __init__(self, master: tk.Tk) -> None:
        self.master = master
        self._toasts: list[tk.Toplevel] = []
        self._y_offset = 20

    def show(self, message: str, toast_type: str = "info", duration: int = 3000) -> None:
        """显示 Toast 通知。

        Args:
            message: 通知内容
            toast_type: "success", "error", "warning", "info"
            duration: 显示时长（毫秒）
        """
        colors = {
            "success": ("#dcfce7", "#16a34a", "#059669"),
            "error": ("#fee2e2", "#dc2626", "#b91c1c"),
            "warning": ("#fef3c7", "#d97706", "#b45309"),
            "info": ("#e0f2fe", "#0369a1", "#0284c7"),
        }
        bg, fg, border = colors.get(toast_type, colors["info"])

        toast = tk.Toplevel(self.master)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        toast.configure(bg=bg)

        # 圆角卡片
        card = tk.Frame(toast, bg=bg, padx=24, pady=12,
                        highlightbackground=border, highlightthickness=1)
        card.pack()

        # 图标
        icons = {"success": "✓", "error": "✕", "warning": "⚠", "info": "ℹ"}
        icon = icons.get(toast_type, "ℹ")

        tk.Label(card, text=f"{icon}  {message}",
                 font=("Microsoft YaHei", 12, "bold"),
                 bg=bg, fg=fg).pack()

        # 定位到屏幕顶部中央
        toast.update_idletasks()
        width = toast.winfo_width()
        x = (self.master.winfo_screenwidth() - width) // 2
        y = self._y_offset
        toast.geometry(f"+{x}+{y}")
        self._y_offset += toast.winfo_height() + 10

        self._toasts.append(toast)

        def dismiss() -> None:
            if toast in self._toasts:
                self._toasts.remove(toast)
            if not self._toasts:
                self._y_offset = 20
            toast.destroy()

        toast.after(duration, dismiss)


# ==================== 按钮涟漪效果 ====================
def _create_ripple(btn: tk.Button) -> None:
    """在按钮位置创建扩散涟漪效果。"""
    parent = btn.master
    btn.update_idletasks()

    x, y = btn.winfo_x(), btn.winfo_y()
    w, h = btn.winfo_width(), btn.winfo_height()

    # 创建涟漪 Label（初始很小，在按钮中心）
    ripple = tk.Label(parent, bg="#34d399", relief=tk.FLAT, bd=0)
    ripple.place(x=x + w // 2, y=y + h // 2, width=0, height=0)

    def animate(step: int = 0) -> None:
        if step >= 10:
            ripple.destroy()
            return

        scale = step / 10
        new_size = int(min(w, h) * scale * 2.5)
        new_x = x + w // 2 - new_size // 2
        new_y = y + h // 2 - new_size // 2

        # 颜色从亮绿渐变到背景色
        r = int(52 + (240 - 52) * (step / 10))
        g = int(211 + (253 - 211) * (step / 10))
        b = int(153 + (244 - 153) * (step / 10))
        color = f"#{r:02x}{g:02x}{b:02x}"

        ripple.config(bg=color)
        ripple.place(x=new_x, y=new_y, width=new_size, height=new_size)

        parent.after(30, lambda: animate(step + 1))

    animate()


# ==================== 药丸按钮工具 ====================
def style_pill_button(btn: tk.Button, bg: str = _PRIMARY, fg: str = "white",
                     hover_bg: str = _PRIMARY_DARK, active_bg: str = _PRIMARY_DARK) -> None:
    """将 tk.Button 配置为 Apple 药丸风格，并添加悬停/按下/涟漪效果。"""
    original_font = ("Microsoft YaHei", 12, "bold")
    small_font = ("Microsoft YaHei", 11, "bold")
    original_padx, original_pady = 24, 8
    small_padx, small_pady = 20, 6

    btn.config(
        bg=bg, fg=fg,
        activebackground=active_bg, activeforeground=fg,
        font=original_font,
        relief=tk.FLAT, bd=0,
        padx=original_padx, pady=original_pady,
        cursor="hand2",
    )

    def on_enter(event, b=btn, h=hover_bg):
        b.config(bg=h)

    def on_leave(event, b=btn, o=bg):
        b.config(bg=bg, font=original_font, padx=original_padx, pady=original_pady)

    def on_press(event, b=btn):
        b.config(font=small_font, padx=small_padx, pady=small_pady)
        _create_ripple(b)

    def on_release(event, b=btn):
        b.config(font=original_font, padx=original_padx, pady=original_pady)

    # 清除旧绑定
    for ev in ("<Enter>", "<Leave>", "<Button-1>", "<ButtonRelease-1>"):
        btn.bind(ev, lambda e: None)

    btn.bind("<Enter>", on_enter)
    btn.bind("<Leave>", on_leave)
    btn.bind("<Button-1>", on_press)
    btn.bind("<ButtonRelease-1>", on_release)


def _update_button_appearance(btn: tk.Button, bg: str, hover_bg: str,
                              active_bg: str) -> None:
    """运行时更新按钮外观和效果（连接/断开切换时用）。"""
    original_font = ("Microsoft YaHei", 12, "bold")
    small_font = ("Microsoft YaHei", 11, "bold")
    original_padx, original_pady = 24, 8
    small_padx, small_pady = 20, 6

    btn.config(bg=bg, activebackground=active_bg)

    def on_enter(event, h=hover_bg):
        btn.config(bg=h)

    def on_leave(event, o=bg):
        btn.config(bg=bg, font=original_font, padx=original_padx, pady=original_pady)

    def on_press(event):
        btn.config(font=small_font, padx=small_padx, pady=small_pady)
        _create_ripple(btn)

    def on_release(event):
        btn.config(font=original_font, padx=original_padx, pady=original_pady)

    # 清除旧绑定
    for ev in ("<Enter>", "<Leave>", "<Button-1>", "<ButtonRelease-1>"):
        btn.bind(ev, lambda e: None)

    btn.bind("<Enter>", on_enter)
    btn.bind("<Leave>", on_leave)
    btn.bind("<Button-1>", on_press)
    btn.bind("<ButtonRelease-1>", on_release)


# ==================== 倒计时弹窗（Apple 卡片风格）====================
class CountdownDialog(tk.Toplevel):
    """可取消的倒计时弹窗 — Apple 卡片风格。"""

    def __init__(self, master: tk.Misc, title: str, message: str, seconds: int) -> None:
        super().__init__(master)
        self.title(title)
        self.configure(bg=_BG)
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self._cancelled = False
        self._remaining = seconds

        # 白色圆角卡片
        card = tk.Frame(self, bg=_CARD_BG, padx=40, pady=30,
                        highlightbackground=_CARD_BORDER, highlightthickness=1)
        card.pack(padx=30, pady=30)

        tk.Label(card, text=message, font=("Microsoft YaHei", 13),
                 bg=_CARD_BG, fg=_TEXT, justify="left").pack(pady=(0, 16))
        self._label = tk.Label(card, text=f"倒计时 {seconds} 秒...",
                               font=("Microsoft YaHei", 28, "bold"),
                               bg=_CARD_BG, fg=_PRIMARY)
        self._label.pack(pady=(0, 20))

        btn = tk.Button(card, text="取消", command=self._on_cancel,
                        font=("Microsoft YaHei", 12, "bold"),
                        bg=_DANGER, fg="white", activebackground=_DANGER_DARK,
                        relief=tk.FLAT, padx=30, pady=8, cursor="hand2", bd=0)
        btn.pack()
        style_pill_button(btn, bg=_DANGER, hover_bg=_DANGER_HOVER, active_bg=_DANGER_DARK)

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self._tick()

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def _on_cancel(self) -> None:
        self._cancelled = True
        self.destroy()

    def _tick(self) -> None:
        if self._cancelled:
            return
        if self._remaining <= 0:
            self.destroy()
            return
        self._label.config(text=f"倒计时 {self._remaining} 秒...")
        self._remaining -= 1
        self.after(1000, self._tick)


# ==================== 主应用 ====================
class WeightApp:
    def __init__(self, master: tk.Tk) -> None:
        self.master = master
        master.title(config.WINDOW_TITLE)
        # 最大化窗口（非全屏）
        master.state('zoomed')

        self.screen_w = master.winfo_screenwidth()
        self.screen_h = master.winfo_screenheight()
        self.bg_color = _BG
        master.configure(bg=self.bg_color)

        # 粒子背景（Apple 风：更淡更少）
        self.bg_canvas = tk.Canvas(master, width=self.screen_w, height=self.screen_h,
                                   bg=self.bg_color, highlightthickness=0)
        self.bg_canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.particles = [BubbleParticle(self.bg_canvas, self.screen_w, self.screen_h) for _ in range(25)]

        # Toast 通知管理器
        self.toast_manager = ToastManager(master)

        # 右上角校徽图片（支持 PyInstaller 打包后的解压目录 sys._MEIPASS）
        try:
            logo_path = resource_path("校徽.png")
            self.logo_image = tk.PhotoImage(file=logo_path)
            # 原图 1142×349，缩放 4 倍后 286×88（保持比例，宽度适合右上角）
            self.logo_image = self.logo_image.subsample(4, 4)
            self.bg_canvas.create_image(
                self.screen_w - 30, 30, image=self.logo_image, anchor="ne"
            )
        except Exception as e:
            # 图片缺失时回退到纯文字
            self.logo_image = None
            self.bg_canvas.create_text(
                self.screen_w - 40, 40, text="北京交通大学",
                font=("FangSong", 22, "bold"), fill=_PRIMARY, anchor="ne"
            )
            print(f"[提示] 校徽图片加载失败，使用纯文字: {e}")
        # 左上角时钟
        self.clock_label_on_canvas = self.bg_canvas.create_text(
            40, 40, text="--:--:--",
            font=("Microsoft YaHei", 14, "bold"), fill=_TEXT_DIM, anchor="nw"
        )

        # 状态
        self.driver: Optional[object] = None
        self.calibrator: Optional[Calibrator] = None
        self.is_simulate = config.SIMULATE_MODE_DEFAULT
        self.connected = False
        self.received_data = False

        # 业务层
        # 硬件已配置中值滤波(3) + 平均滤波(3)，软件直接使用返回值
        # 管道：硬件输出 → 稳定判定 → 显示
        self.stable_judge = StableJudge(thresh=config.STABLE_THRESH_GRAMS,
                                        count_required=config.STABLE_COUNT_REQUIRED)
        self.accumulator = WeightAccumulator()

        self.last_raw_grams: float = 0.0
        self.last_filtered_grams: float = 0.0
        self.last_display_grams: float = 0.0
        self.last_total_grams: float = 0.0

        # 状态机状态徽章用
        self._prev_state = "IDLE"

        # 去皮后跳过旧帧计数
        self._discard_frames = 0

        # 去皮操作状态（后台线程）
        self._tare_in_progress = False

        # 连接心跳
        self._last_data_time: float = 0.0

        # UI
        self.create_widgets()

        # 主循环
        self.update_display()
        self.update_particles()
        self.update_clock()
        master.protocol("WM_DELETE_WINDOW", self.on_closing)

    # ============= UI =============

    def create_widgets(self) -> None:
        """Apple 风格卡片式布局：
            ┌─ 粒子背景 + 右上角 LOGO + 左上角时钟 ─┐
            │                                       │
            │  ┌─────────────────────────────┐     │
            │  │         葱称重系统           │     │
            │  │                             │     │
            │  │         当前重量            │     │
            │  │           0           g     │     │
            │  │                             │     │
            │  │    累计总重: 0 g  [清零总重] │     │
            │  └─────────────────────────────┘     │
            │                                       │
            │  ┌─────────────────────────────┐     │
            │  │  串口设置 / 去皮操作        │     │
            │  └─────────────────────────────┘     │
            └────────────────────────────────────────┘
        """
        # ============= 中心显示区（白色卡片） =============
        main_frame = tk.Frame(self.master, bg=_CARD_BG,
                              highlightbackground=_CARD_BORDER,
                              highlightthickness=1)
        main_frame.place(relx=0.5, rely=0.42, anchor=tk.CENTER,
                         width=640, height=480)

        # 大标题
        tk.Label(main_frame, text="葱称重系统", font=("Microsoft YaHei", 36, "bold"),
                 bg=_CARD_BG, fg=_TEXT).pack(pady=(30, 10))

        # "当前重量"标签
        tk.Label(main_frame, text="当前重量", font=("Microsoft YaHei", 14),
                 bg=_CARD_BG, fg=_TEXT_DIM).pack(pady=(10, 0))

        # 数字 + 单位
        weight_display = tk.Frame(main_frame, bg=_CARD_BG)
        weight_display.pack(pady=20)

        self.weight_label = tk.Label(weight_display, text="0",
                                      font=("Consolas", 96, "bold"),
                                      bg=_CARD_BG, fg=_PRIMARY)
        self.weight_label.pack(side=tk.LEFT, padx=(0, 8))
        tk.Label(weight_display, text="g", font=("Microsoft YaHei", 32),
                 bg=_CARD_BG, fg=_PRIMARY).pack(side=tk.LEFT, pady=(30, 0))

        # 平滑动画器
        self.weight_animator = SmoothNumberAnimator(
            self.weight_label,
            color_stable=_PRIMARY,
            color_active=_PRIMARY_LIGHT
        )

        # 累计总重 + 清零
        total_frame = tk.Frame(main_frame, bg=_CARD_BG)
        total_frame.pack(pady=20)
        self.total_label = tk.Label(total_frame, text="累计总重: 0 g",
                                     font=("Microsoft YaHei", 18),
                                     bg=_CARD_BG, fg=_TEXT)
        self.total_label.pack(side=tk.LEFT, padx=20)

        self.clear_btn = tk.Button(total_frame, text="清零总重", command=self.clear_total,
                                    bg=_PRIMARY, fg="white",
                                    font=("Microsoft YaHei", 12, "bold"),
                                    relief=tk.FLAT, padx=22, pady=8, bd=0,
                                    cursor="hand2")
        self.clear_btn.pack(side=tk.LEFT, padx=20)
        style_pill_button(self.clear_btn)

        # ============= 底部设置区（白色卡片） =============
        settings_card = tk.Frame(self.master, bg=_CARD_BG,
                                  highlightbackground=_CARD_BORDER,
                                  highlightthickness=1)
        settings_card.place(relx=0.5, rely=0.85, anchor=tk.CENTER,
                            width=800, height=160)

        # 内部 padding
        inner = tk.Frame(settings_card, bg=_CARD_BG)
        inner.pack(fill=tk.BOTH, expand=True, padx=30, pady=16)

        # 第 1 行：串口设置
        row1 = tk.Frame(inner, bg=_CARD_BG)
        row1.pack(pady=4, fill=tk.X)

        tk.Label(row1, text="串口设置", font=("Microsoft YaHei", 11, "bold"),
                 bg=_CARD_BG, fg=_TEXT_DIM).pack(side=tk.LEFT, padx=(0, 20))

        # 端口
        tk.Label(row1, text="端口", font=("Microsoft YaHei", 11),
                 bg=_CARD_BG, fg=_TEXT_DIM).pack(side=tk.LEFT, padx=(0, 6))
        self.port_combo = ttk.Combobox(row1, width=12, font=("Microsoft YaHei", 11),
                                       state='readonly')
        self.port_combo.pack(side=tk.LEFT, padx=(0, 16))
        self.refresh_ports()

        ttk.Button(row1, text="刷新", command=self.refresh_ports,
                   style="Soft.TButton").pack(side=tk.LEFT, padx=(0, 16))

        # 波特率
        tk.Label(row1, text="波特率", font=("Microsoft YaHei", 11),
                 bg=_CARD_BG, fg=_TEXT_DIM).pack(side=tk.LEFT, padx=(0, 6))
        self.baud_combo = ttk.Combobox(row1,
                                       values=['2400', '4800', '9600', '19200', '28800',
                                               '38400', '57600', '115200'],
                                       width=12, font=("Microsoft YaHei", 11),
                                       state='readonly')
        self.baud_combo.set(str(config.SERIAL_BAUDRATE))
        self.baud_combo.pack(side=tk.LEFT, padx=(0, 16))

        # 连接按钮 + 状态
        self.connect_btn = tk.Button(row1, text="连接", command=self.toggle_connection,
                                      bg=_PRIMARY, fg="white", activebackground=_PRIMARY_DARK,
                                      font=("Microsoft YaHei", 12, "bold"),
                                      width=10, relief=tk.FLAT, pady=6,
                                      cursor="hand2", bd=0)
        self.connect_btn.pack(side=tk.LEFT, padx=(0, 16))
        style_pill_button(self.connect_btn)

        self.status_label = tk.Label(row1, text="未连接",
                                      bg=_CARD_BG, fg=_DANGER,
                                      font=("Microsoft YaHei", 11, "bold"))
        self.status_label.pack(side=tk.LEFT)

        # 第 2 行：去皮操作
        row2 = tk.Frame(inner, bg=_CARD_BG)
        row2.pack(pady=4, fill=tk.X)

        tk.Label(row2, text="会话操作", font=("Microsoft YaHei", 11, "bold"),
                 bg=_CARD_BG, fg=_TEXT_DIM).pack(side=tk.LEFT, padx=(0, 20))

        self.tare_btn = tk.Button(row2, text="去皮（重新置零）", command=self.do_tare,
                                    bg="#e2e8f0", fg=_TEXT,
                                    font=("Microsoft YaHei", 11, "bold"),
                                    relief=tk.FLAT, padx=18, pady=6,
                                    cursor="hand2", state=tk.DISABLED, bd=0)
        self.tare_btn.pack(side=tk.LEFT, padx=(0, 12))

        self.untare_btn = tk.Button(row2, text="取消去皮", command=self.do_untare,
                                      bg="#e2e8f0", fg=_TEXT,
                                      font=("Microsoft YaHei", 11, "bold"),
                                      relief=tk.FLAT, padx=18, pady=6,
                                      cursor="hand2", state=tk.DISABLED, bd=0)
        self.untare_btn.pack(side=tk.LEFT, padx=(0, 12))

        # 状态机状态提示（IDLE / WEIGHING）
        self.state_badge = tk.Label(row2, text="●  IDLE",
                                     bg=_CARD_BG, fg="#94a3b8",
                                     font=("Microsoft YaHei", 11, "bold"))
        self.state_badge.pack(side=tk.RIGHT)

        # 应用 ttk 软按钮样式
        self._configure_soft_button_style()

    def _configure_soft_button_style(self) -> None:
        """配置刷新按钮的软样式（浅绿底）。"""
        s = ttk.Style()
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        s.configure("Soft.TButton",
                    font=("Microsoft YaHei", 11, "bold"),
                    foreground=_TEXT,
                    background="#e2e8f0",
                    borderwidth=0,
                    focusthickness=0,
                    padding=(12, 6),
                    relief="flat")
        s.map("Soft.TButton",
              background=[("active", "#cbd5e1")])

    # ============= 串口管理 =============
    def refresh_ports(self) -> None:
        ports = list_serial_ports()
        self.port_combo['values'] = ports
        if ports:
            self.port_combo.set(ports[0])
        else:
            self.port_combo.set('')

    def toggle_connection(self) -> None:
        if not self.connected:
            self.connect()
        else:
            self.disconnect()

    def connect(self) -> None:
        if self.is_simulate:
            self.driver = SimulatedScaleDriver()
        else:
            port = self.port_combo.get().strip()
            baud_str = self.baud_combo.get().strip()
            if not port or not baud_str:
                self.toast_manager.show("请选择串口号和波特率", "error")
                return
            try:
                baud = int(baud_str)
            except ValueError:
                self.toast_manager.show("波特率无效", "error")
                return
            self.driver = ScaleDriver(port=port, baud=baud)

        try:
            self.driver.open()
        except ScaleConnectionError as e:
            self.toast_manager.show(f"连接失败：{e}", "error")
            self.driver = None
            return

        try:
            self.driver.start_auto_send(mode=1)
        except Exception:
            pass

        self.connected = True
        self.received_data = False
        self.stable_judge.reset()
        self.accumulator.clear_total()
        self.last_raw_grams = 0.0
        self.last_filtered_grams = 0.0
        self.last_display_grams = 0.0
        self.last_total_grams = 0.0
        self._discard_frames = 0
        self._last_data_time = time.time()
        # 立即重置显示
        self.weight_animator.set_value(0)
        self.total_label.config(text="累计总重: 0 g")

        self.calibrator = Calibrator(self.driver)

        # UI 更新
        self.connect_btn.config(text="断开")
        _update_button_appearance(self.connect_btn, _DANGER, _DANGER_HOVER, _DANGER_DARK)
        for btn in (self.tare_btn, self.untare_btn):
            btn.config(state=tk.NORMAL)
        if self.is_simulate:
            self.status_label.config(text="虚拟测试模式", fg="#0369a1")
        else:
            self.status_label.config(text="已连接", fg=_PRIMARY)

        # 每次连接后自动去皮
        if config.AUTO_TARE_ON_CONNECT:
            self._auto_tare_flow()

    def _auto_tare_flow(self) -> None:
        dlg = CountdownDialog(
            self.master,
            title="自动去皮",
            message=("请确认托盘状态已稳定（空载或带容器均可）。\n"
                     "程序将在倒计时结束后把当前重量视为 0。"),
            seconds=config.AUTO_TARE_COUNTDOWN_SECONDS,
        )
        self.master.wait_window(dlg)
        if dlg.cancelled:
            self.status_label.config(text=("虚拟测试模式" if self.is_simulate else "已连接（未去皮）"),
                                       fg="#c47a1a")
            return
        # 使用后台线程执行去皮，不阻塞 UI
        # reset_total=True：清除倒计时期间容器重量被误累计到总重的值
        self._run_calibrator_action("tare", reset_total=True)

    def disconnect(self) -> None:
        if self.driver is not None:
            try:
                self.driver.close()
            except Exception:
                pass
        self.driver = None
        self.calibrator = None
        self.connected = False
        self.received_data = False
        self._tare_in_progress = False
        # 重置显示（提示用户数据已失效）
        self.last_display_grams = 0.0
        self.last_total_grams = 0.0
        self._shown_grams = None
        self.weight_animator.set_value(0)
        self.total_label.config(text="累计总重: -- g")
        self.state_badge.config(text="●  未连接", fg="#94a3b8")
        self._prev_state = "DISCONNECTED"
        # UI
        self.connect_btn.config(text="连接")
        _update_button_appearance(self.connect_btn, _PRIMARY, _PRIMARY_DARK, _PRIMARY_DARK)
        self.status_label.config(text="未连接", fg=_DANGER)
        for btn in (self.tare_btn, self.untare_btn):
            btn.config(state=tk.DISABLED)

    # ============= 会话级操作 =============
    def _ensure_connected(self) -> bool:
        if not self.connected or self.calibrator is None:
            self.toast_manager.show("请先连接电子秤", "warning")
            return False
        return True

    def _reset_after_tare(self) -> None:
        """去皮成功后：重置显示状态 + 跳过旧帧（不清空总重）。"""
        self.stable_judge.force_set(0.0)
        self.last_display_grams = 0.0
        self._shown_grams = None  # 强制下次刷新 Label
        self._discard_frames = 5  # 跳过前5帧旧数据（约500ms）
        self.weight_animator.set_value(0)

    def _run_calibrator_action(self, action_name: str, reset_total: bool = False) -> None:
        """在后台线程执行去皮/取消去皮（避免阻塞 UI）。

        reset_total=True 时，去皮成功后同时清零总重（用于连接时自动去皮）。
        """
        if self._tare_in_progress:
            return
        if not self._ensure_connected():
            return
        self._tare_in_progress = True
        self._tare_reset_total = reset_total
        # 禁用操作按钮，显示操作状态
        for btn in (self.tare_btn, self.untare_btn, self.connect_btn):
            btn.config(state=tk.DISABLED)
        action_text = "去皮中..." if action_name == "tare" else "取消去皮中..."
        self.status_label.config(text=action_text, fg="#c47a1a")

        result_box = {"ok": False}

        def worker():
            try:
                if action_name == "tare":
                    result_box["ok"] = self.calibrator.tare()
                else:
                    result_box["ok"] = self.calibrator.untare()
            except Exception:
                result_box["ok"] = False

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        self._poll_calibrator_done(t, action_name, result_box)

    def _poll_calibrator_done(self, thread: threading.Thread, action_name: str,
                              result_box: dict) -> None:
        """轮询后台线程完成状态，完成后更新 UI。"""
        if thread.is_alive():
            self.master.after(50, lambda: self._poll_calibrator_done(
                thread, action_name, result_box))
            return
        self._tare_in_progress = False
        # 恢复按钮状态
        for btn in (self.tare_btn, self.untare_btn):
            btn.config(state=tk.NORMAL)
        self.connect_btn.config(text="断开")
        _update_button_appearance(self.connect_btn, _DANGER, _DANGER_HOVER, _DANGER_DARK)

        if result_box["ok"]:
            if action_name == "tare":
                self._reset_after_tare()
                if self._tare_reset_total:
                    self.accumulator.clear_total()
                    self.last_total_grams = 0.0
                    self.total_label.config(text="累计总重: 0 g")
                self.status_label.config(
                    text="虚拟测试模式" if self.is_simulate else "已重新去皮",
                    fg=_PRIMARY)
            else:
                self.status_label.config(
                    text="虚拟测试模式" if self.is_simulate else "已取消去皮",
                    fg="#c47a1a")
        else:
            action_cn = "去皮" if action_name == "tare" else "取消去皮"
            self.status_label.config(
                text="虚拟测试模式" if self.is_simulate else "已连接",
                fg=_PRIMARY)
            self.toast_manager.show(f"{action_cn}失败", "error")

    def do_tare(self) -> None:
        self._run_calibrator_action("tare")

    def do_untare(self) -> None:
        self._run_calibrator_action("untare")

    def clear_total(self) -> None:
        if self.connected and self.received_data:
            self.accumulator.clear_total()
            self.last_total_grams = 0.0
            self.total_label.config(text="累计总重: 0 g")
        else:
            self.toast_manager.show("未连接设备或无有效数据，无法清零", "warning")

    # ============= 业务循环 =============
    def update_particles(self) -> None:
        for p in self.particles:
            p.move()
        self.master.after(40, self.update_particles)

    def update_clock(self) -> None:
        self.bg_canvas.itemconfig(self.clock_label_on_canvas,
                                  text=time.strftime("%H:%M:%S"))
        self.master.after(1000, self.update_clock)

    def update_display(self) -> None:
        """读取所有帧 → 稳定判定 → 状态机 → 更新显示。

        硬件已配置中值滤波(3) + 平均滤波(3)，软件直接使用返回值。
        管道：硬件输出 → 稳定判定 → 显示
        总重累计：使用显示值（而非峰值），保证"总重 = 用户看到的值之和"
        显示精度：1g 分辨率，显示整数
        """
        if self.connected and self.driver is not None and not self._tare_in_progress:
            try:
                frames = self.driver.read_frames()
            except ScaleConnectionError as e:
                self._connection_lost(str(e))
                self.master.after(config.UI_UPDATE_INTERVAL, self.update_display)
                return

            for frame in frames:
                # 去皮后跳过旧帧（串口缓冲区残留的去皮前数据）
                if self._discard_frames > 0:
                    self._discard_frames -= 1
                    continue

                grams = weight_ticks_to_grams(
                    frame["weight_ticks"],
                    frame["sign"],
                    grams_per_tick=config.GRAMS_PER_TICK,
                )
                self.last_raw_grams = grams
                self.last_filtered_grams = grams  # 硬件已滤波，直接使用
                self.received_data = True
                self._last_data_time = time.time()
                # 稳定判定
                _, display_val = self.stable_judge.update(grams)
                display_val = max(0.0, display_val)
                # 状态机：用硬件返回值判阈值，用显示值累计总重
                event = self.accumulator.update(grams, display_val)
                if event is not None:
                    # 物品离场：立即把显示归 0（不显示下降过程）
                    self.stable_judge.force_set(0.0)
                    display_val = 0.0
                elif (self.accumulator.state == "WEIGHING"
                      and self.accumulator._locked):
                    # 锁定后冻结显示：不显示推板下压导致的升高值
                    display_val = self.accumulator.locked_weight
                self.last_display_grams = display_val

            # 连接心跳检测：超过 N 秒未收到任何数据，视为断开
            if self.received_data and self._last_data_time > 0:
                elapsed = time.time() - self._last_data_time
                if elapsed > config.CONNECTION_TIMEOUT_SECONDS:
                    self._connection_lost("超过 {} 秒未收到数据，连接可能已断开".format(
                        int(config.CONNECTION_TIMEOUT_SECONDS)))
                    self.master.after(config.UI_UPDATE_INTERVAL, self.update_display)
                    return

        # 只在稳定值变化时更新 Label（使用平滑动画 + 颜色跟随）
        if self.last_display_grams != getattr(self, "_shown_grams", None):
            self.weight_animator.set_value(self.last_display_grams)
            self._shown_grams = self.last_display_grams

        # 总重：整数显示
        total_now = self.accumulator.total_weight
        if total_now != self.last_total_grams:
            self.total_label.config(text=f"累计总重: {int(round(total_now))} g")
            self.last_total_grams = total_now

        # 状态机徽章 + 粒子颜色响应
        new_state = self.accumulator.state
        if new_state != self._prev_state:
            self._update_state_badge(new_state)
            # 粒子颜色随状态变化
            for p in self.particles:
                p.set_active(new_state == "WEIGHING")
            self._prev_state = new_state

        self.master.after(config.UI_UPDATE_INTERVAL, self.update_display)

    def _connection_lost(self, reason: str) -> None:
        """连接丢失处理：断开并提示用户。"""
        self.disconnect()
        self.toast_manager.show(
            f"连接断开：{reason}，请检查 USB 连接后重新点击「连接」",
            "error"
        )

    def _update_state_badge(self, state: str) -> None:
        if state == "WEIGHING":
            self.state_badge.config(text="●  WEIGHING · 称重中", fg="#16a34a")
        else:
            self.state_badge.config(text="●  IDLE · 空闲", fg="#94a3b8")

    # ============= 退出 =============
    def on_closing(self) -> None:
        if self.driver is not None:
            try:
                self.driver.close()
            except Exception:
                pass
        self.master.destroy()
