"""
大葱称重系统 UI（Tkinter 现代化卡片风）。

适配 1kg 量程 HX711 TTL 变送器电子秤（CMCU-07 协议 V3.70）。

设计风格：现代企业 SaaS 卡片风
- 浅色背景 + 阴影圆角卡片
- ttk.Style 主题化（clam 主题）
- 实时数据用 ttk 组件 + Canvas 圆角进度环
- 数字变化带 200ms 平滑过渡
- 状态徽章带颜色 chip（成功/警告/危险/中性）
- 历史记录区滚动显示最近称重记录

主要功能:
- 实时重量显示（大数字 + 进度环），不显示爬升/下降中间值（稳定后才更新）
- 累计总重 + 本次称重峰值 + 累计件数
- 设备状态卡（连接/未连接 + COM/波特率/地址/量程/模式）
- 历史记录区（每件物品离场后追加记录）
- 串口连接管理（自动发送模式）
- 连接后自动去皮（3 秒倒计时）
- 会话级去皮操作（去皮/取消去皮）
- 虚拟测试模式（无需电子秤）
"""
from __future__ import annotations

import math
import random
import time
import tkinter as tk
from collections import deque
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
from weight_filter import MovingAverageFilter, StableJudge
from weight_state import WeightAccumulator


# ==================== 管理员权限 ====================
def is_admin() -> bool:
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def run_as_admin() -> None:
    if is_admin():
        return
    try:
        import ctypes
        import sys
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1
        )
        sys.exit()
    except Exception as e:
        print(f"无法获取管理员权限: {e}")


# ==================== 圆角卡片（Canvas 拼接）====================
def _create_rounded_rect(canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int,
                          radius: int, fill: str, outline: str = "", width: int = 1) -> int:
    """在 canvas 上画一个圆角矩形。返回最后一个 item id。"""
    r = min(radius, (x2 - x1) // 2, (y2 - y1) // 2)
    if r <= 0:
        return canvas.create_rectangle(x1, y1, x2, y2, fill=fill, outline=outline, width=width)
    pts = [
        x1 + r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1,
    ]
    return canvas.create_polygon(pts, fill=fill, outline=outline, width=width, smooth=True)


def create_card(parent: tk.Misc, x: int, y: int, w: int, h: int, radius: int = 16,
                fill: str = "#ffffff", border: str = "#e2e8f0",
                shadow: bool = True) -> tk.Frame:
    """创建一张带阴影和圆角的卡片，返回承载子组件的 Frame。"""
    shadow_offset = 4 if shadow else 0
    # 阴影 canvas
    if shadow:
        shadow_canvas = tk.Canvas(parent, width=w + 8, height=h + 8,
                                  bg=config.THEME["bg"], highlightthickness=0, bd=0)
        shadow_canvas.place(x=x + shadow_offset, y=y + shadow_offset, width=w, height=h)
        # 浅灰色阴影（Tcl 不支持 8 位 hex）
        _create_rounded_rect(shadow_canvas, 0, 0, w, h, radius, fill="#cbd5e1", outline="")
    # 卡片 canvas
    canvas = tk.Canvas(parent, width=w, height=h, bg=config.THEME["bg"],
                       highlightthickness=0, bd=0)
    canvas.place(x=x, y=y, width=w, height=h)
    _create_rounded_rect(canvas, 0, 0, w, h, radius, fill=fill, outline=border)
    # 在 Canvas 上浮一个透明 Frame 用来放实际控件
    inner = tk.Frame(canvas, bg=fill)
    inner.place(x=2, y=2, width=w - 4, height=h - 4)
    return inner


# ==================== 数字平滑过渡 ====================
class AnimatedNumber:
    """一个会平滑过渡到目标值的数字。"""

    def __init__(self, initial: float = 0.0) -> None:
        self.current = float(initial)
        self.target = float(initial)

    def set_target(self, value: float) -> None:
        self.target = float(value)

    def step(self, factor: float = 0.25) -> bool:
        """朝目标值移动一小步，返回是否有变化。"""
        diff = self.target - self.current
        if abs(diff) < 0.05:
            if self.current != self.target:
                self.current = self.target
                return True
            return False
        self.current += diff * factor
        return True


# ==================== 倒计时弹窗 ====================
class CountdownDialog(tk.Toplevel):
    """可取消的倒计时弹窗（沿用旧版但用 THEME 配色）。"""

    def __init__(self, master: tk.Misc, title: str, message: str, seconds: int) -> None:
        super().__init__(master)
        self.title(title)
        self.configure(bg=config.THEME["bg"])
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self._cancelled = False
        self._remaining = seconds

        bg = config.THEME["card_bg"]
        fg = config.THEME["text"]

        card = tk.Frame(self, bg=bg, padx=30, pady=25,
                        highlightbackground=config.THEME["card_border"],
                        highlightthickness=1)
        card.pack(padx=20, pady=20)

        tk.Label(card, text=message, font=(config.THEME["font_zh"], 12),
                 bg=bg, fg=fg, justify="left").pack(pady=(0, 12))
        self._label = tk.Label(card, text=f"倒计时 {seconds} 秒...",
                               font=(config.THEME["font_zh"], 22, "bold"),
                               bg=bg, fg=config.THEME["warning"])
        self._label.pack(pady=(0, 15))

        btn = tk.Button(card, text="取消", command=self._on_cancel,
                        font=(config.THEME["font_zh"], 11, "bold"),
                        bg=config.THEME["danger"], fg="white",
                        activebackground=config.THEME["danger"],
                        relief=tk.FLAT, padx=20, pady=6, cursor="hand2", bd=0)
        btn.pack()

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
        self.theme = config.THEME

        master.title(config.WINDOW_TITLE)
        master.attributes('-fullscreen', True)
        master.bind("<Escape>", self.toggle_fullscreen)
        self.is_fullscreen = True
        master.configure(bg=self.theme["bg"])

        # 屏幕尺寸
        self.screen_w = master.winfo_screenwidth()
        self.screen_h = master.winfo_screenheight()

        # 状态
        self.driver: Optional[object] = None
        self.calibrator: Optional[Calibrator] = None
        self.is_simulate = config.SIMULATE_MODE_DEFAULT
        self.connected = False
        self.received_data = False

        # 业务层
        self.filter = MovingAverageFilter(window_size=config.FILTER_WINDOW_SIZE)
        self.stable_judge = StableJudge(thresh=config.STABLE_THRESH_GRAMS,
                                        count_required=config.STABLE_COUNT_REQUIRED)
        self.accumulator = WeightAccumulator()

        # 动画数字
        self.weight_anim = AnimatedNumber(0.0)
        self.total_anim = AnimatedNumber(0.0)
        self.last_display_grams = 0.0

        # 历史记录（最近 50 笔，新条目在顶部）
        self.history: deque = deque(maxlen=config.HISTORY_MAX_RECORDS)

        # 状态机相关
        self._pulse_counter = 0
        self._pulse_toggle = False

        # 风格
        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self._configure_styles()

        # UI
        self.create_widgets()

        # 主循环
        self.update_display()
        self.update_clock()
        master.protocol("WM_DELETE_WINDOW", self.on_closing)

    # ============= 主题样式 =============
    def _configure_styles(self) -> None:
        t = self.theme
        s = self.style

        # 全局基础
        s.configure(".", font=(t["font_zh"], 10), background=t["bg"], foreground=t["text"])
        s.configure("Card.TFrame", background=t["card_bg"])
        s.configure("Panel.TFrame", background=t["panel_bg"])

        # 标题
        s.configure("Title.TLabel",
                    font=(t["font_zh"], 16, "bold"),
                    background=t["card_bg"],
                    foreground=t["text"])
        s.configure("Subtitle.TLabel",
                    font=(t["font_zh"], 11),
                    background=t["card_bg"],
                    foreground=t["text_dim"])
        s.configure("Caption.TLabel",
                    font=(t["font_zh"], 9),
                    background=t["card_bg"],
                    foreground=t["muted_dark"])

        # 数字大字号
        s.configure("BigNumber.TLabel",
                    font=(t["font_zh"], 64, "bold"),
                    background=t["card_bg"],
                    foreground=t["primary"])
        s.configure("MidNumber.TLabel",
                    font=(t["font_zh"], 36, "bold"),
                    background=t["card_bg"],
                    foreground=t["text"])
        s.configure("Unit.TLabel",
                    font=(t["font_zh"], 16),
                    background=t["card_bg"],
                    foreground=t["muted_dark"])

        # 按钮（圆角扁平）
        s.configure("Primary.TButton",
                    font=(t["font_zh"], 11, "bold"),
                    foreground="white",
                    background=t["primary"],
                    borderwidth=0,
                    focusthickness=0,
                    padding=(18, 8),
                    relief="flat")
        s.map("Primary.TButton",
              background=[("active", t["primary_dark"]), ("disabled", t["muted"])])

        s.configure("Danger.TButton",
                    font=(t["font_zh"], 11, "bold"),
                    foreground="white",
                    background=t["danger"],
                    borderwidth=0,
                    focusthickness=0,
                    padding=(18, 8),
                    relief="flat")
        s.map("Danger.TButton",
              background=[("active", "#b91c1c"), ("disabled", t["muted"])])

        s.configure("Secondary.TButton",
                    font=(t["font_zh"], 11, "bold"),
                    foreground=t["accent_dark"],
                    background=t["accent_light"],
                    borderwidth=0,
                    focusthickness=0,
                    padding=(18, 8),
                    relief="flat")
        s.map("Secondary.TButton",
              background=[("active", "#bae6fd")])

        # Combobox
        s.configure("Modern.TCombobox",
                    fieldbackground="white",
                    background=t["accent"],
                    foreground=t["text"],
                    arrowcolor=t["muted_dark"],
                    padding=4)
        s.map("Modern.TCombobox",
              fieldbackground=[("readonly", "white")],
              foreground=[("readonly", t["text"])])

        # 状态徽章
        for name, bg, fg in [
            ("Success", t["success"], "white"),
            ("Warning", t["warning"], "white"),
            ("Danger",  t["danger"],  "white"),
            ("Info",    t["accent"],  "white"),
            ("Muted",   t["muted"],   "white"),
        ]:
            s.configure(f"Status.{name}.TLabel",
                        font=(t["font_zh"], 10, "bold"),
                        foreground=fg,
                        background=bg,
                        padding=(12, 5))

        # 历史记录项
        s.configure("HistoryIndex.TLabel",
                    font=(t["font_zh"], 10, "bold"),
                    background=t["card_bg"],
                    foreground=t["accent"],
                    padding=(0, 0))
        s.configure("HistoryWeight.TLabel",
                    font=(t["font_zh"], 14, "bold"),
                    background=t["card_bg"],
                    foreground=t["text"])
        s.configure("HistoryTime.TLabel",
                    font=(t["font_zh"], 9),
                    background=t["card_bg"],
                    foreground=t["muted_dark"])
        s.configure("HistoryDivider.TFrame", background=t["card_border"])

    # ============= 窗口控制 =============
    def toggle_fullscreen(self, event=None) -> None:
        self.is_fullscreen = not self.is_fullscreen
        self.master.attributes('-fullscreen', self.is_fullscreen)

    # ============= UI 构建 =============
    def create_widgets(self) -> None:
        t = self.theme
        # 网格：顶栏(0) / 主体(1) / 徽章条(2) / 底栏(3)
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(1, weight=1)
        self.master.rowconfigure(2, weight=0)

        self._create_topbar()
        self._create_cards_area()
        self._create_status_bar()
        self._create_bottombar()

    # ---- 顶栏 ----
    def _create_topbar(self) -> None:
        t = self.theme
        topbar = tk.Frame(self.master, bg=t["topbar_bg"], height=60)
        topbar.grid(row=0, column=0, sticky="ew")
        topbar.pack_propagate(False)

        # 项目标题
        title_frame = tk.Frame(topbar, bg=t["topbar_bg"])
        title_frame.pack(side=tk.LEFT, padx=30, pady=10)
        tk.Label(title_frame, text="⓪",
                 font=(t["font_zh"], 18, "bold"),
                 bg=t["topbar_bg"], fg=t["primary"]).pack(side=tk.LEFT, padx=(0, 8))
        tk.Label(title_frame, text="北京交通大学 · 智慧农业装备 · 大葱称重上位机",
                 font=(t["font_zh"], 13, "bold"),
                 bg=t["topbar_bg"], fg=t["text"]).pack(side=tk.LEFT)

        # 右侧：时钟 + 版本
        right = tk.Frame(topbar, bg=t["topbar_bg"])
        right.pack(side=tk.RIGHT, padx=30, pady=10)
        self.clock_label = tk.Label(right, text="--:--:--",
                                    font=(t["font_zh"], 14, "bold"),
                                    bg=t["topbar_bg"], fg=t["text_dim"])
        self.clock_label.pack(side=tk.LEFT, padx=(0, 20))
        tk.Label(right, text="v2.2",
                 font=(t["font_zh"], 11),
                 bg=t["topbar_bg"], fg=t["muted_dark"]).pack(side=tk.LEFT)

        # 底部分隔线
        sep = tk.Frame(self.master, bg=t["card_border"], height=1)
        sep.grid(row=0, column=0, sticky="sew")

    # ---- 主体卡片区 ----
    def _create_cards_area(self) -> None:
        t = self.theme
        area = tk.Frame(self.master, bg=t["bg"])
        area.grid(row=1, column=0, sticky="nsew", padx=30, pady=15)

        # 4 列：3 卡片 + 1 历史记录
        # 卡片宽 420，高 ~360
        card_w = 420
        card_h = 360
        gap = 20
        total_w = card_w * 4 + gap * 3
        offset_x = max(0, (self.screen_w - total_w) // 2)

        # 卡片 1：当前重量
        self.card1 = create_card(area, offset_x, 0, card_w, card_h, radius=t["radius"])
        self._build_card1(self.card1)

        # 卡片 2：累计总重
        self.card2 = create_card(area, offset_x + (card_w + gap), 0, card_w, card_h, radius=t["radius"])
        self._build_card2(self.card2)

        # 卡片 3：设备状态
        self.card3 = create_card(area, offset_x + (card_w + gap) * 2, 0, card_w, card_h, radius=t["radius"])
        self._build_card3(self.card3)

        # 卡片 4：历史记录
        self.card4 = create_card(area, offset_x + (card_w + gap) * 3, 0, card_w, card_h, radius=t["radius"])
        self._build_card4(self.card4)

    def _build_card1(self, parent: tk.Frame) -> None:
        t = self.theme
        # 标题区
        head = tk.Frame(parent, bg=t["card_bg"])
        head.pack(fill=tk.X, padx=24, pady=(20, 0))
        tk.Label(head, text="⚖  当前重量", font=(t["font_zh"], 14, "bold"),
                 bg=t["card_bg"], fg=t["text"]).pack(side=tk.LEFT)
        self.weight_unit_label = tk.Label(head, text="g", font=(t["font_zh"], 11),
                                          bg=t["card_bg"], fg=t["muted_dark"])
        self.weight_unit_label.pack(side=tk.RIGHT)

        # 进度环 + 数字
        body = tk.Frame(parent, bg=t["card_bg"])
        body.pack(fill=tk.BOTH, expand=True, padx=24, pady=10)

        arc_size = 200
        self.weight_arc = tk.Canvas(body, width=arc_size, height=arc_size,
                                    bg=t["card_bg"], highlightthickness=0, bd=0)
        self.weight_arc.pack(side=tk.LEFT, padx=(0, 16))

        right = tk.Frame(body, bg=t["card_bg"])
        right.pack(side=tk.LEFT, fill=tk.Y, expand=True)

        self.weight_value_label = tk.Label(right, text="0.0",
                                           font=(t["font_zh"], 56, "bold"),
                                           bg=t["card_bg"], fg=t["primary"])
        self.weight_value_label.pack(anchor="w", pady=(30, 0))
        tk.Label(right, text="克 (g)", font=(t["font_zh"], 12),
                 bg=t["card_bg"], fg=t["muted_dark"]).pack(anchor="w")

        # 进度条
        bar_frame = tk.Frame(parent, bg=t["card_bg"])
        bar_frame.pack(fill=tk.X, padx=24, pady=(0, 16))
        tk.Label(bar_frame, text="量程进度", font=(t["font_zh"], 9),
                 bg=t["card_bg"], fg=t["muted_dark"]).pack(anchor="w")
        self.progress_canvas = tk.Canvas(bar_frame, height=8,
                                         bg=t["card_bg"], highlightthickness=0, bd=0)
        self.progress_canvas.pack(fill=tk.X, pady=(4, 2))
        self.progress_label = tk.Label(bar_frame, text="0 / 1000 g (0%)",
                                       font=(t["font_zh"], 9),
                                       bg=t["card_bg"], fg=t["muted_dark"])
        self.progress_label.pack(anchor="e")

    def _build_card2(self, parent: tk.Frame) -> None:
        t = self.theme
        head = tk.Frame(parent, bg=t["card_bg"])
        head.pack(fill=tk.X, padx=24, pady=(20, 0))
        tk.Label(head, text="📊  累计统计", font=(t["font_zh"], 14, "bold"),
                 bg=t["card_bg"], fg=t["text"]).pack(side=tk.LEFT)

        body = tk.Frame(parent, bg=t["card_bg"])
        body.pack(fill=tk.BOTH, expand=True, padx=24, pady=10)

        tk.Label(body, text="累计总重", font=(t["font_zh"], 10),
                 bg=t["card_bg"], fg=t["muted_dark"]).pack(anchor="w")
        total_row = tk.Frame(body, bg=t["card_bg"])
        total_row.pack(anchor="w", pady=(4, 0))
        self.total_value_label = tk.Label(total_row, text="0.0",
                                          font=(t["font_zh"], 48, "bold"),
                                          bg=t["card_bg"], fg=t["text"])
        self.total_value_label.pack(side=tk.LEFT)
        tk.Label(total_row, text=" g", font=(t["font_zh"], 16),
                 bg=t["card_bg"], fg=t["muted_dark"]).pack(side=tk.LEFT, pady=(20, 0))

        # 分割
        tk.Frame(body, bg=t["card_border"], height=1).pack(fill=tk.X, pady=16)

        # 副信息：本次峰值 + 累计件数
        sub = tk.Frame(body, bg=t["card_bg"])
        sub.pack(fill=tk.X)
        # 本次峰值
        col1 = tk.Frame(sub, bg=t["card_bg"])
        col1.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(col1, text="本次峰值", font=(t["font_zh"], 10),
                 bg=t["card_bg"], fg=t["muted_dark"]).pack(anchor="w")
        self.peak_label = tk.Label(col1, text="0.0 g",
                                   font=(t["font_zh"], 18, "bold"),
                                   bg=t["card_bg"], fg=t["accent_dark"])
        self.peak_label.pack(anchor="w", pady=(2, 0))
        # 累计件数
        col2 = tk.Frame(sub, bg=t["card_bg"])
        col2.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(col2, text="累计件数", font=(t["font_zh"], 10),
                 bg=t["card_bg"], fg=t["muted_dark"]).pack(anchor="w")
        self.count_label = tk.Label(col2, text="0 件",
                                    font=(t["font_zh"], 18, "bold"),
                                    bg=t["card_bg"], fg=t["accent_dark"])
        self.count_label.pack(anchor="w", pady=(2, 0))

        # 清零按钮
        btn_row = tk.Frame(parent, bg=t["card_bg"])
        btn_row.pack(fill=tk.X, padx=24, pady=(0, 20))
        ttk.Button(btn_row, text="清零累计", style="Secondary.TButton",
                   command=self.clear_total).pack(side=tk.RIGHT)

    def _build_card3(self, parent: tk.Frame) -> None:
        t = self.theme
        head = tk.Frame(parent, bg=t["card_bg"])
        head.pack(fill=tk.X, padx=24, pady=(20, 0))
        tk.Label(head, text="🔌  设备状态", font=(t["font_zh"], 14, "bold"),
                 bg=t["card_bg"], fg=t["text"]).pack(side=tk.LEFT)

        body = tk.Frame(parent, bg=t["card_bg"])
        body.pack(fill=tk.BOTH, expand=True, padx=24, pady=10)

        # 连接状态（大徽章）
        self.device_state_label = ttk.Label(body, text="●  未连接",
                                            style="Status.Muted.TLabel")
        self.device_state_label.pack(anchor="w", pady=(4, 16))

        # 设备信息列表
        info_frame = tk.Frame(body, bg=t["card_bg"])
        info_frame.pack(fill=tk.X)

        self.info_labels = {}
        rows = [
            ("串口", "—"),
            ("波特率", "—"),
            ("模块地址", f"0x{config.MODULE_ADDRESS:02X}"),
            ("分辨率", f"{config.GRAMS_PER_TICK} g/tick"),
            ("量程", "1.0 kg"),
            ("协议", "V3.70"),
        ]
        for i, (k, v) in enumerate(rows):
            row = tk.Frame(info_frame, bg=t["card_bg"])
            row.pack(fill=tk.X, pady=4)
            tk.Label(row, text=k, font=(t["font_zh"], 10),
                     bg=t["card_bg"], fg=t["muted_dark"],
                     width=10, anchor="w").pack(side=tk.LEFT)
            lbl = tk.Label(row, text=v, font=(t["font_zh"], 10, "bold"),
                           bg=t["card_bg"], fg=t["text"], anchor="w")
            lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.info_labels[k] = lbl

    def _build_card4(self, parent: tk.Frame) -> None:
        t = self.theme
        head = tk.Frame(parent, bg=t["card_bg"])
        head.pack(fill=tk.X, padx=24, pady=(20, 0))
        tk.Label(head, text="📜  称重记录", font=(t["font_zh"], 14, "bold"),
                 bg=t["card_bg"], fg=t["text"]).pack(side=tk.LEFT)
        self.history_count_label = tk.Label(head, text="0",
                                            font=(t["font_zh"], 10),
                                            bg=t["card_bg"], fg=t["muted_dark"])
        self.history_count_label.pack(side=tk.RIGHT)

        # 滚动区
        list_frame = tk.Frame(parent, bg=t["card_bg"])
        list_frame.pack(fill=tk.BOTH, expand=True, padx=24, pady=(8, 16))

        canvas = tk.Canvas(list_frame, bg=t["card_bg"],
                           highlightthickness=0, bd=0, height=240)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        self.history_inner = tk.Frame(canvas, bg=t["card_bg"])

        self.history_inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.history_inner, anchor="nw", width=370)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.history_canvas = canvas

    def _add_history_record_widget(self, idx: int, weight: float, ts: str) -> tk.Frame:
        """在历史记录区添加一行。"""
        t = self.theme
        item = tk.Frame(self.history_inner, bg=t["card_bg"], height=46)
        item.pack(fill=tk.X, pady=(0, 6))
        item.pack_propagate(False)

        # 序号徽章
        badge_w = 28
        badge = tk.Canvas(item, width=badge_w, height=28,
                          bg=t["card_bg"], highlightthickness=0, bd=0)
        badge.pack(side=tk.LEFT, padx=(0, 8), pady=9)
        _create_rounded_rect(badge, 0, 0, badge_w, 28, 6, fill=t["accent_light"], outline="")
        badge.create_text(badge_w / 2, 14, text=str(idx),
                          font=(t["font_zh"], 10, "bold"),
                          fill=t["accent_dark"])

        # 重量 + 时间
        text_col = tk.Frame(item, bg=t["card_bg"])
        text_col.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=6)
        weight_text = f"{weight:.1f} g"
        tk.Label(text_col, text=weight_text,
                 font=(t["font_zh"], 14, "bold"),
                 bg=t["card_bg"], fg=t["text"], anchor="w").pack(anchor="w")
        tk.Label(text_col, text=ts,
                 font=(t["font_zh"], 9),
                 bg=t["card_bg"], fg=t["muted_dark"], anchor="w").pack(anchor="w")

        return item

    # ---- 状态徽章条 ----
    def _create_status_bar(self) -> None:
        t = self.theme
        bar = tk.Frame(self.master, bg=t["bg"], height=50)
        bar.grid(row=2, column=0, sticky="ew", padx=30, pady=(0, 10))

        # 居中
        inner = tk.Frame(bar, bg=t["bg"])
        inner.pack(expand=True)

        # 4 个徽章
        self.badge_state = ttk.Label(inner, text="●  IDLE", style="Status.Muted.TLabel")
        self.badge_tare = ttk.Label(inner, text="●  未去皮", style="Status.Warning.TLabel")
        self.badge_mode = ttk.Label(inner, text="●  实时模式", style="Status.Info.TLabel")
        self.badge_range = ttk.Label(inner, text="●  1.0 kg · 0.1g", style="Status.Info.TLabel")

        for b in (self.badge_state, self.badge_tare, self.badge_mode, self.badge_range):
            b.pack(side=tk.LEFT, padx=6)

    # ---- 底栏 ----
    def _create_bottombar(self) -> None:
        t = self.theme
        bar = tk.Frame(self.master, bg=t["panel_bg"], height=110)
        bar.grid(row=3, column=0, sticky="ew")
        bar.pack_propagate(False)

        # 顶部分割
        tk.Frame(bar, bg=t["card_border"], height=1).pack(side=tk.TOP, fill=tk.X)

        inner = tk.Frame(bar, bg=t["panel_bg"])
        inner.pack(fill=tk.BOTH, expand=True, padx=30, pady=12)

        # 左侧：串口设置
        left = tk.Frame(inner, bg=t["panel_bg"])
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 30))

        tk.Label(left, text="串口设置", font=(t["font_zh"], 10, "bold"),
                 bg=t["panel_bg"], fg=t["muted_dark"]).pack(anchor="w", pady=(0, 6))

        row = tk.Frame(left, bg=t["panel_bg"])
        row.pack(anchor="w")

        tk.Label(row, text="端口", font=(t["font_zh"], 10),
                 bg=t["panel_bg"], fg=t["text_dim"]).pack(side=tk.LEFT, padx=(0, 4))
        self.port_combo = ttk.Combobox(row, width=10, font=(t["font_zh"], 10),
                                       state='readonly', style="Modern.TCombobox")
        self.port_combo.pack(side=tk.LEFT, padx=(0, 12))
        self.refresh_ports()

        ttk.Button(row, text="刷新", style="Secondary.TButton",
                   command=self.refresh_ports).pack(side=tk.LEFT, padx=(0, 12))

        tk.Label(row, text="波特率", font=(t["font_zh"], 10),
                 bg=t["panel_bg"], fg=t["text_dim"]).pack(side=tk.LEFT, padx=(0, 4))
        self.baud_combo = ttk.Combobox(row,
                                       values=['2400', '4800', '9600', '19200', '28800',
                                               '38400', '57600', '115200'],
                                       width=10, font=(t["font_zh"], 10),
                                       state='readonly', style="Modern.TCombobox")
        self.baud_combo.set(str(config.SERIAL_BAUDRATE))
        self.baud_combo.pack(side=tk.LEFT, padx=(0, 12))

        self.connect_btn = ttk.Button(row, text="●  连接",
                                      style="Primary.TButton",
                                      command=self.toggle_connection)
        self.connect_btn.pack(side=tk.LEFT)

        # 右侧：操作按钮
        right = tk.Frame(inner, bg=t["panel_bg"])
        right.pack(side=tk.RIGHT, fill=tk.Y)

        tk.Label(right, text="称重操作", font=(t["font_zh"], 10, "bold"),
                 bg=t["panel_bg"], fg=t["muted_dark"]).pack(anchor="e", pady=(0, 6))

        btn_row = tk.Frame(right, bg=t["panel_bg"])
        btn_row.pack(anchor="e")

        self.tare_btn = ttk.Button(btn_row, text="去皮（重新置零）",
                                   style="Secondary.TButton",
                                   command=self.do_tare, state=tk.DISABLED)
        self.tare_btn.pack(side=tk.LEFT, padx=4)

        self.untare_btn = ttk.Button(btn_row, text="取消去皮",
                                     style="Secondary.TButton",
                                     command=self.do_untare, state=tk.DISABLED)
        self.untare_btn.pack(side=tk.LEFT, padx=4)

        self.clear_history_btn = ttk.Button(btn_row, text="清空记录",
                                            style="Secondary.TButton",
                                            command=self.clear_history)
        self.clear_history_btn.pack(side=tk.LEFT, padx=4)

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
        t = self.theme
        if self.is_simulate:
            self.driver = SimulatedScaleDriver()
        else:
            port = self.port_combo.get().strip()
            baud_str = self.baud_combo.get().strip()
            if not port or not baud_str:
                messagebox.showerror("错误", "请选择串口号和波特率")
                return
            try:
                baud = int(baud_str)
            except ValueError:
                messagebox.showerror("错误", "波特率无效")
                return
            self.driver = ScaleDriver(port=port, baud=baud)

        try:
            self.driver.open()
        except ScaleConnectionError as e:
            messagebox.showerror("连接失败", str(e))
            self.driver = None
            return

        try:
            self.driver.start_auto_send(mode=1)
        except Exception:
            pass

        self.connected = True
        self.received_data = False
        self.filter.reset()
        self.stable_judge.reset()
        self.accumulator.clear_total()
        self.weight_anim.current = 0.0
        self.weight_anim.target = 0.0
        self.total_anim.current = 0.0
        self.total_anim.target = 0.0
        self.last_display_grams = 0.0
        self.clear_history()

        self.calibrator = Calibrator(self.driver)

        # 更新设备信息
        if self.is_simulate:
            self.info_labels["串口"].config(text="虚拟 COM", fg=t["accent_dark"])
            self.info_labels["波特率"].config(text="—")
            self.badge_mode.config(text="●  虚拟模式", style="Status.Info.TLabel")
        else:
            self.info_labels["串口"].config(text=self.port_combo.get(), fg=t["text"])
            self.info_labels["波特率"].config(text=self.baud_combo.get() + " 8N1", fg=t["text"])
            self.badge_mode.config(text="●  实时模式", style="Status.Info.TLabel")

        # UI 状态
        self.connect_btn.config(text="●  断开", style="Danger.TButton")
        for btn in (self.tare_btn, self.untare_btn):
            btn.config(state=tk.NORMAL)
        self.device_state_label.config(text="●  已连接", style="Status.Success.TLabel")

        if config.AUTO_TARE_ON_CONNECT:
            self._auto_tare_flow()

    def _auto_tare_flow(self) -> None:
        t = self.theme
        dlg = CountdownDialog(
            self.master,
            title="自动去皮",
            message=("请确认托盘状态已稳定（空载或带容器均可）。\n"
                     "程序将在倒计时结束后把当前重量视为 0。"),
            seconds=config.AUTO_TARE_COUNTDOWN_SECONDS,
        )
        self.master.wait_window(dlg)
        if dlg.cancelled:
            self.badge_tare.config(text="●  未去皮", style="Status.Warning.TLabel")
            return
        if self.calibrator is None:
            return
        self.badge_tare.config(text="●  去皮中…", style="Status.Warning.TLabel")
        self.master.update()
        ok = self.calibrator.tare()
        if ok:
            self.badge_tare.config(text="●  已去皮", style="Status.Success.TLabel")
        else:
            self.badge_tare.config(text="●  去皮失败", style="Status.Danger.TLabel")
            messagebox.showwarning("去皮失败", "自动去皮未成功，请手动点击'去皮'重试。")

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
        self.connect_btn.config(text="●  连接", style="Primary.TButton")
        self.device_state_label.config(text="●  未连接", style="Status.Muted.TLabel")
        self.badge_tare.config(text="●  未去皮", style="Status.Warning.TLabel")
        self.info_labels["串口"].config(text="—", fg=self.theme["muted_dark"])
        self.info_labels["波特率"].config(text="—", fg=self.theme["muted_dark"])
        for btn in (self.tare_btn, self.untare_btn):
            btn.config(state=tk.DISABLED)

    # ============= 会话级操作 =============
    def _ensure_connected(self) -> bool:
        if not self.connected or self.calibrator is None:
            messagebox.showinfo("提示", "请先连接电子秤")
            return False
        return True

    def do_tare(self) -> None:
        if not self._ensure_connected():
            return
        if self.calibrator.tare():
            self.badge_tare.config(text="●  已去皮", style="Status.Success.TLabel")
        else:
            self.badge_tare.config(text="●  去皮失败", style="Status.Danger.TLabel")
            messagebox.showerror("失败", "去皮失败")

    def do_untare(self) -> None:
        if not self._ensure_connected():
            return
        if self.calibrator.untare():
            self.badge_tare.config(text="●  未去皮", style="Status.Warning.TLabel")
        else:
            messagebox.showerror("失败", "取消去皮失败")

    def clear_total(self) -> None:
        if self.connected and self.received_data:
            self.accumulator.clear_total()
            self.total_anim.set_target(0.0)
        else:
            messagebox.showinfo("提示", "未连接设备或无有效数据，无法清零")

    def clear_history(self) -> None:
        for w in self.history_inner.winfo_children():
            w.destroy()
        self.history.clear()
        self.history_count_label.config(text="0")

    # ============= 进度环 =============
    def _draw_progress_arc(self, current_g: float, max_g: float = 1000.0) -> None:
        t = self.theme
        size = 200
        pad = 18
        c = self.weight_arc
        c.delete("all")
        # 背景环
        c.create_oval(pad, pad, size - pad, size - pad,
                      outline=t["card_border"], width=14)
        # 进度环
        ratio = min(1.0, max(0.0, current_g / max_g))
        if ratio > 0.001:
            extent = -ratio * 360
            c.create_arc(pad, pad, size - pad, size - pad,
                         start=90, extent=extent,
                         outline=t["primary"], width=14, style=tk.ARC)
        # 中心百分比
        c.create_text(size / 2, size / 2 - 10, text=f"{ratio*100:.0f}%",
                      font=(t["font_zh"], 14, "bold"),
                      fill=t["text_dim"])
        c.create_text(size / 2, size / 2 + 12, text=f"{current_g:.0f}/{max_g:.0f}g",
                      font=(t["font_zh"], 9),
                      fill=t["muted_dark"])

    def _draw_progress_bar(self, current_g: float, max_g: float = 1000.0) -> None:
        t = self.theme
        c = self.progress_canvas
        c.delete("all")
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 2:
            return
        # 背景
        _create_rounded_rect(c, 0, 0, w, h, 4, fill=t["card_border"], outline="")
        # 进度
        ratio = min(1.0, max(0.0, current_g / max_g))
        fill_w = int(w * ratio)
        if fill_w > 4:
            _create_rounded_rect(c, 0, 0, fill_w, h, 4, fill=t["primary"], outline="")
        # 标签
        self.progress_label.config(text=f"{current_g:.0f} / {max_g:.0f} g ({ratio*100:.0f}%)")

    # ============= 主循环 =============
    def update_clock(self) -> None:
        self.clock_label.config(text=time.strftime("%H:%M:%S"))
        self.master.after(1000, self.update_clock)

    def update_display(self) -> None:
        t = self.theme

        if self.connected and self.driver is not None:
            try:
                frame = self.driver.read_frame()
            except ScaleConnectionError as e:
                self.disconnect()
                messagebox.showerror("串口错误", f"与设备的连接已丢失：{e}")
                self.master.after(config.UI_UPDATE_INTERVAL, self.update_display)
                return

            if frame is not None:
                grams = weight_ticks_to_grams(
                    frame["weight_ticks"],
                    frame["sign"],
                    grams_per_tick=config.GRAMS_PER_TICK,
                )
                self.last_raw_grams = grams
                filtered = self.filter.update(grams)
                self.received_data = True
                # 状态机
                event = self.accumulator.update(filtered)
                if event is not None:
                    self.stable_judge.force_set(0.0)
                    self._on_item_weighed(event)
                # 稳定判定
                _, display_val = self.stable_judge.update(filtered)
                display_val = max(0.0, display_val)
                self.last_display_grams = display_val
                self.weight_anim.set_target(display_val)
                self.total_anim.set_target(self.accumulator.total_weight)

        # 数字平滑
        self.weight_anim.step(factor=0.3)
        self.total_anim.step(factor=0.2)

        # 更新大数字
        self.weight_value_label.config(text=f"{self.weight_anim.current:.1f}")
        self.total_value_label.config(text=f"{self.total_anim.current:.1f}")
        self.peak_label.config(text=f"{self.accumulator.peak_weight:.1f} g")
        self.count_label.config(text=f"{self.accumulator.event_count} 件")

        # 进度环
        self._draw_progress_arc(self.weight_anim.current, 1000.0)
        self._draw_progress_bar(self.weight_anim.current, 1000.0)

        # 状态徽章
        self._update_state_badge()

        self.master.after(config.UI_UPDATE_INTERVAL, self.update_display)

    def _on_item_weighed(self, event: dict) -> None:
        """物品离场：追加历史记录 + 更新本次峰值显示。"""
        weight = event["weight_g"]
        ts = time.strftime("%H:%M:%S")
        # 计入历史
        self.history.appendleft((weight, ts))
        self.history_count_label.config(text=str(len(self.history)))
        # 重建历史 widget（简单粗暴：全部重画）
        for w in self.history_inner.winfo_children():
            w.destroy()
        for i, (w, t_) in enumerate(self.history, 1):
            self._add_history_record_widget(i, w, t_)
        # 滚到顶部
        self.history_canvas.yview_moveto(0)

    def _update_state_badge(self) -> None:
        # 状态机
        if self.accumulator.state == "WEIGHING":
            # 脉冲
            self._pulse_counter += 1
            if self._pulse_counter % 4 == 0:
                self._pulse_toggle = not self._pulse_toggle
            color_bg = self.theme["primary"] if self._pulse_toggle else self.theme["primary_dark"]
            self.badge_state.config(text="●  WEIGHING", background=color_bg)
        else:
            self.badge_state.config(text="●  IDLE",
                                    style="Status.Muted.TLabel",
                                    background=self.theme["muted"])

    # ============= 退出 =============
    def on_closing(self) -> None:
        if self.driver is not None:
            try:
                self.driver.close()
            except Exception:
                pass
        self.master.destroy()
