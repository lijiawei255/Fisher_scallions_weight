"""
大葱称重系统 UI（Tkinter）。

适配 1kg 量程 HX711 TTL 变送器电子秤（CMCU-07 协议 V3.70）。

整体布局沿用 v2.2 简洁风格（中心大字 + 底部设置面板），但用更现代的字体
（数字用 Microsoft YaHei 增强辨识度，中文仍用仿宋）和更协调的配色。

主要功能:
- 实时重量显示（g，1 位小数）— 稳定后才显示，不显示爬升/下降中间值
- 累计总重 + 清零
- 串口连接管理（自动发送模式）
- 连接后自动去皮（3 秒可取消倒计时）
- 运行时去皮 / 取消去皮
- 虚拟测试模式（无需电子秤）
"""
from __future__ import annotations

import random
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
from weight_filter import MovingAverageFilter, StableJudge
from weight_state import WeightAccumulator


# ==================== 自动请求管理员权限 ====================
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


# ==================== 粒子装饰（背景）====================
class Particle:
    def __init__(self, canvas: tk.Canvas, width: int, height: int) -> None:
        self.canvas = canvas
        self.width = width
        self.height = height
        self.x = random.randint(0, width)
        self.y = random.randint(0, height)
        self.vx = random.uniform(-0.4, 0.4)
        self.vy = random.uniform(-0.4, 0.4)
        self.radius = random.randint(1, 3)
        # 4 档浅绿色，与浅色背景和谐
        self.color = random.choice(['#d1e7d1', '#b9d9b9', '#9fca9f', '#7eb47e'])
        self.id = canvas.create_oval(
            self.x - self.radius, self.y - self.radius,
            self.x + self.radius, self.y + self.radius,
            fill=self.color, outline="",
        )

    def move(self) -> None:
        self.x += self.vx
        self.y += self.vy
        if self.x <= 0 or self.x >= self.width:
            self.vx *= -1
        if self.y <= 0 or self.y >= self.height:
            self.vy *= -1
        self.canvas.coords(
            self.id,
            self.x - self.radius, self.y - self.radius,
            self.x + self.radius, self.y + self.radius,
        )


# ==================== 倒计时弹窗 ====================
class CountdownDialog(tk.Toplevel):
    """可取消的倒计时弹窗。"""

    def __init__(self, master: tk.Misc, title: str, message: str, seconds: int) -> None:
        super().__init__(master)
        self.title(title)
        self.configure(bg=config.THEME["bg"])
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self._cancelled = False
        self._remaining = seconds

        # 用白底圆角卡片
        card = tk.Frame(self, bg="#ffffff", padx=30, pady=20,
                        highlightbackground="#d4e6d4", highlightthickness=1)
        card.pack(padx=20, pady=20)

        tk.Label(card, text=message, font=("Microsoft YaHei", 12),
                 bg="#ffffff", fg="#333", justify="left").pack(pady=(0, 12))
        self._label = tk.Label(card, text=f"倒计时 {seconds} 秒...",
                               font=("Microsoft YaHei", 20, "bold"),
                               bg="#ffffff", fg="#c47a1a")
        self._label.pack(pady=(0, 15))

        btn = tk.Button(card, text="取消", command=self._on_cancel,
                        font=("Microsoft YaHei", 11, "bold"),
                        bg="#c0392b", fg="white", activebackground="#a93226",
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
        master.title(config.WINDOW_TITLE)
        master.attributes('-fullscreen', True)
        master.bind("<Escape>", self.toggle_fullscreen)
        self.is_fullscreen = True

        self.screen_w = master.winfo_screenwidth()
        self.screen_h = master.winfo_screenheight()
        self.bg_color = config.BG_COLOR
        master.configure(bg=self.bg_color)

        # 粒子背景
        self.bg_canvas = tk.Canvas(master, width=self.screen_w, height=self.screen_h,
                                   bg=self.bg_color, highlightthickness=0)
        self.bg_canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.particles = [Particle(self.bg_canvas, self.screen_w, self.screen_h) for _ in range(40)]

        # 右上角校徽图片
        try:
            self.logo_image = tk.PhotoImage(file="校徽.png")
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
                font=("FangSong", 22, "bold"), fill="#2d5e2d", anchor="ne"
            )
            print(f"[提示] 校徽图片加载失败，使用纯文字: {e}")
        # 左上角时钟
        self.clock_label_on_canvas = self.bg_canvas.create_text(
            40, 40, text="--:--:--",
            font=("Microsoft YaHei", 14, "bold"), fill="#475569", anchor="nw"
        )

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

        self.last_raw_grams: float = 0.0
        self.last_filtered_grams: float = 0.0
        self.last_display_grams: float = 0.0
        self.last_total_grams: float = 0.0

        # 状态机状态徽章用
        self._prev_state = "IDLE"

        # UI
        self.create_widgets()

        # 主循环
        self.update_display()
        self.update_particles()
        self.update_clock()
        master.protocol("WM_DELETE_WINDOW", self.on_closing)

    # ============= UI =============
    def toggle_fullscreen(self, event=None) -> None:
        self.is_fullscreen = not self.is_fullscreen
        self.master.attributes('-fullscreen', self.is_fullscreen)

    def create_widgets(self) -> None:
        """整体布局：
            ┌─ 粒子背景 + 右上角 LOGO + 左上角时钟 ─┐
            │                                       │
            │     葱称重系统（大标题）               │
            │     当前重量（小字）                   │
            │     30.0 g（巨字）                    │
            │     累计总重: 30.0 g   [清零总重]     │
            │                                       │
            ├─ 底部设置面板 ─────────────────────┤
            │  串口/波特率/连接/状态              │
            │  去皮 / 取消去皮                     │
            └────────────────────────────────────┘
        """
        # ============= 中心显示区 =============
        main_frame = tk.Frame(self.master, bg=self.bg_color)
        main_frame.place(relx=0.5, rely=0.42, anchor=tk.CENTER)

        # 大标题
        tk.Label(main_frame, text="葱称重系统", font=("FangSong", 40, "bold"),
                 bg=self.bg_color, fg="#1e4d1e").pack(pady=(0, 40))

        # 当前重量
        weight_frame = tk.Frame(main_frame, bg=self.bg_color)
        weight_frame.pack(pady=10)
        tk.Label(weight_frame, text="当前重量", font=("FangSong", 20),
                 bg=self.bg_color, fg="#475569").pack()
        # 巨字（数字用 Microsoft YaHei 加粗，单位用 FangSong）
        big_row = tk.Frame(weight_frame, bg=self.bg_color)
        big_row.pack(pady=10)
        self.weight_label = tk.Label(big_row, text="0.0",
                                      font=("Microsoft YaHei", 96, "bold"),
                                      bg=self.bg_color, fg="#2d5e2d")
        self.weight_label.pack(side=tk.LEFT, padx=(0, 8))
        tk.Label(big_row, text="g", font=("FangSong", 32),
                 bg=self.bg_color, fg="#2d5e2d").pack(side=tk.LEFT, pady=(30, 0))

        # 累计总重 + 清零
        total_frame = tk.Frame(main_frame, bg=self.bg_color)
        total_frame.pack(pady=30)
        self.total_label = tk.Label(total_frame, text="累计总重: 0.0 g",
                                     font=("FangSong", 24),
                                     bg=self.bg_color, fg="#1e4d1e")
        self.total_label.pack(side=tk.LEFT, padx=20)
        self.clear_btn = tk.Button(total_frame, text="清零总重", command=self.clear_total,
                                    bg="#5a9e5a", fg="white", activebackground="#4d8a4d",
                                    font=("Microsoft YaHei", 14, "bold"),
                                    relief=tk.FLAT, padx=22, pady=8, cursor="hand2", bd=0)
        self.clear_btn.pack(side=tk.LEFT, padx=20)

        # ============= 底部设置区 =============
        settings = tk.Frame(self.master, bg="#e6f0e6", relief=tk.FLAT)
        settings.place(relx=0.5, rely=0.88, anchor=tk.CENTER, width=1200, height=140)

        # 内部 padding
        inner = tk.Frame(settings, bg="#e6f0e6")
        inner.pack(fill=tk.BOTH, expand=True, padx=30, pady=10)

        # 第 1 行：串口设置
        row1 = tk.Frame(inner, bg="#e6f0e6")
        row1.pack(pady=4, fill=tk.X)
        tk.Label(row1, text="串口设置", font=("Microsoft YaHei", 11, "bold"),
                 bg="#e6f0e6", fg="#475569").pack(side=tk.LEFT, padx=(0, 20))

        # 端口
        tk.Label(row1, text="端口", font=("Microsoft YaHei", 11),
                 bg="#e6f0e6", fg="#475569").pack(side=tk.LEFT, padx=(0, 6))
        self.port_combo = ttk.Combobox(row1, width=12, font=("Microsoft YaHei", 11),
                                       state='readonly')
        self.port_combo.pack(side=tk.LEFT, padx=(0, 16))
        self.refresh_ports()

        ttk.Button(row1, text="刷新", command=self.refresh_ports,
                   style="Soft.TButton").pack(side=tk.LEFT, padx=(0, 16))

        # 波特率
        tk.Label(row1, text="波特率", font=("Microsoft YaHei", 11),
                 bg="#e6f0e6", fg="#475569").pack(side=tk.LEFT, padx=(0, 6))
        self.baud_combo = ttk.Combobox(row1,
                                       values=['2400', '4800', '9600', '19200', '28800',
                                               '38400', '57600', '115200'],
                                       width=12, font=("Microsoft YaHei", 11),
                                       state='readonly')
        self.baud_combo.set(str(config.SERIAL_BAUDRATE))
        self.baud_combo.pack(side=tk.LEFT, padx=(0, 16))

        # 连接按钮 + 状态
        self.connect_btn = tk.Button(row1, text="连接", command=self.toggle_connection,
                                      bg="#5a9e5a", fg="white", activebackground="#4d8a4d",
                                      font=("Microsoft YaHei", 12, "bold"),
                                      width=10, relief=tk.FLAT, pady=6,
                                      cursor="hand2", bd=0)
        self.connect_btn.pack(side=tk.LEFT, padx=(0, 16))

        self.status_label = tk.Label(row1, text="未连接",
                                      bg="#e6f0e6", fg="#a94442",
                                      font=("Microsoft YaHei", 11, "bold"))
        self.status_label.pack(side=tk.LEFT)

        # 第 2 行：去皮操作
        row2 = tk.Frame(inner, bg="#e6f0e6")
        row2.pack(pady=4, fill=tk.X)
        tk.Label(row2, text="会话操作", font=("Microsoft YaHei", 11, "bold"),
                 bg="#e6f0e6", fg="#475569").pack(side=tk.LEFT, padx=(0, 20))
        self.tare_btn = tk.Button(row2, text="去皮（重新置零）", command=self.do_tare,
                                    bg="#7ab07a", fg="white", activebackground="#5e955e",
                                    font=("Microsoft YaHei", 11, "bold"),
                                    relief=tk.FLAT, padx=18, pady=6,
                                    cursor="hand2", state=tk.DISABLED, bd=0)
        self.tare_btn.pack(side=tk.LEFT, padx=(0, 12))
        self.untare_btn = tk.Button(row2, text="取消去皮", command=self.do_untare,
                                      bg="#7ab07a", fg="white", activebackground="#5e955e",
                                      font=("Microsoft YaHei", 11, "bold"),
                                      relief=tk.FLAT, padx=18, pady=6,
                                      cursor="hand2", state=tk.DISABLED, bd=0)
        self.untare_btn.pack(side=tk.LEFT, padx=(0, 12))

        # 状态机状态提示（IDLE / WEIGHING）
        self.state_badge = tk.Label(row2, text="●  IDLE",
                                     bg="#e6f0e6", fg="#94a3b8",
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
                    foreground="#1e4d1e",
                    background="#a8d5a8",
                    borderwidth=0,
                    focusthickness=0,
                    padding=(12, 6),
                    relief="flat")
        s.map("Soft.TButton",
              background=[("active", "#8bc08b")])

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
        self.last_raw_grams = 0.0
        self.last_filtered_grams = 0.0
        self.last_display_grams = 0.0
        self.last_total_grams = 0.0
        # 立即重置显示
        self.weight_label.config(text="0.0")
        self.total_label.config(text="累计总重: 0.0 g")

        self.calibrator = Calibrator(self.driver)

        # UI 更新
        self.connect_btn.config(text="断开", bg="#c0392b", activebackground="#a93226")
        for btn in (self.tare_btn, self.untare_btn):
            btn.config(state=tk.NORMAL)
        if self.is_simulate:
            self.status_label.config(text="虚拟测试模式", fg="#0369a1")
        else:
            self.status_label.config(text="已连接", fg="#15803d")

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
        if self.calibrator is None:
            return
        self.status_label.config(text="去皮中...", fg="#c47a1a")
        self.master.update()
        ok = self.calibrator.tare()
        if ok:
            self.status_label.config(text=("虚拟测试模式" if self.is_simulate else "已连接 · 已去皮"),
                                       fg="#15803d")
        else:
            self.status_label.config(text=("虚拟测试模式" if self.is_simulate else "已连接（去皮失败）"),
                                       fg="#a94442")
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
        self.connect_btn.config(text="连接", bg="#5a9e5a", activebackground="#4d8a4d")
        self.status_label.config(text="未连接", fg="#a94442")
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
            self.status_label.config(text=("虚拟测试模式" if self.is_simulate else "已重新去皮"),
                                       fg="#15803d")
        else:
            messagebox.showerror("失败", "去皮失败")

    def do_untare(self) -> None:
        if not self._ensure_connected():
            return
        if self.calibrator.untare():
            self.status_label.config(text=("虚拟测试模式" if self.is_simulate else "已取消去皮"),
                                       fg="#c47a1a")
        else:
            messagebox.showerror("失败", "取消去皮失败")

    def clear_total(self) -> None:
        if self.connected and self.received_data:
            self.accumulator.clear_total()
            self.last_total_grams = 0.0
            self.total_label.config(text="累计总重: 0.0 g")
        else:
            messagebox.showinfo("提示", "未连接设备或无有效数据，无法清零")

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
        """读取一帧 → 滤波 → 状态机 → 稳定判定 → 更新显示。

        关键：只把"稳定值"赋给 self.last_display_grams，每次只在它变化时才
        更新 Label.config(text=...)——这样不会显示爬升/下降过程中的中间值。
        """
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
                self.last_filtered_grams = filtered
                self.received_data = True
                # 状态机
                event = self.accumulator.update(filtered)
                if event is not None:
                    # 物品离场：立即把显示归 0（不显示下降过程）
                    self.stable_judge.force_set(0.0)
                # 稳定判定
                _, display_val = self.stable_judge.update(filtered)
                display_val = max(0.0, display_val)
                self.last_display_grams = display_val

        # ===== 关键修复：只在稳定值变化时更新 Label，避免平滑动画产生中间值 =====
        # （之前 v2.3 用 AnimatedNumber 平滑，会显示 0→9→15→22→26→30 等中间值）
        if self.last_display_grams != getattr(self, "_shown_grams", None):
            self.weight_label.config(text=f"{self.last_display_grams:.1f}")
            self._shown_grams = self.last_display_grams

        # 总重：直接显示（每次物品离场时 total_weight 整数跳变，不会有中间值）
        total_now = self.accumulator.total_weight
        if total_now != self.last_total_grams:
            self.total_label.config(text=f"累计总重: {total_now:.1f} g")
            self.last_total_grams = total_now

        # 状态机徽章
        new_state = self.accumulator.state
        if new_state != self._prev_state:
            self._update_state_badge(new_state)
            self._prev_state = new_state

        self.master.after(config.UI_UPDATE_INTERVAL, self.update_display)

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
