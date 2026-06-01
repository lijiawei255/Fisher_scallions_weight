"""
大葱称重系统 UI（Tkinter）。

适配 1kg 量程 HX711 TTL 变送器电子秤（CMCU-07 协议 V3.70）。

主要功能:
- 实时重量显示（g，1 位小数）
- 累计总重显示 + 清零
- 串口连接管理（自动发送模式）
- 首次连接后自动零点校准（可取消）
- 手动校准入口：零点 / 砝码 / 去皮
- 虚拟测试模式（无需电子秤）
"""
from __future__ import annotations

import random
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from typing import Optional

import config
from calibration import Calibrator
from scale_driver import (
    ScaleDriver,
    SimulatedScaleDriver,
    ScaleConnectionError,
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


# ==================== 粒子装饰 ====================
class Particle:
    def __init__(self, canvas: tk.Canvas, width: int, height: int) -> None:
        self.canvas = canvas
        self.width = width
        self.height = height
        self.x = random.randint(0, width)
        self.y = random.randint(0, height)
        self.vx = random.uniform(-0.5, 0.5)
        self.vy = random.uniform(-0.5, 0.5)
        self.radius = random.randint(1, 3)
        self.color = random.choice(['#e6f5e6', '#d4ecd4', '#c2e6c2', '#b0dfb0'])
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
        self.configure(bg=config.BG_COLOR)
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self._cancelled = False
        self._remaining = seconds

        tk.Label(self, text=message, font=("仿宋", 14), bg=config.BG_COLOR, fg="#333").pack(padx=20, pady=(15, 5))
        self._label = tk.Label(self, text=f"倒计时 {seconds} 秒...", font=("仿宋", 18, "bold"),
                                bg=config.BG_COLOR, fg="#a94442")
        self._label.pack(padx=20, pady=5)

        btn_frame = tk.Frame(self, bg=config.BG_COLOR)
        btn_frame.pack(padx=20, pady=(5, 15))
        tk.Button(btn_frame, text="取消", command=self._on_cancel, font=("仿宋", 12),
                  bg="#b34b4b", fg="white", relief=tk.FLAT, padx=15, pady=5, cursor="hand2").pack()

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
        self.canvas = tk.Canvas(master, width=self.screen_w, height=self.screen_h,
                                bg=self.bg_color, highlightthickness=0)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.particles = [Particle(self.canvas, self.screen_w, self.screen_h) for _ in range(30)]

        # 北京交通大学 LOGO
        self.canvas.create_text(
            self.screen_w - 50, 50, text="北京交通大学",
            font=("仿宋", 24, "bold"), fill="#2d5e2d", anchor="ne"
        )

        # 状态变量
        self.driver: Optional[object] = None  # ScaleDriver 或 SimulatedScaleDriver
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

        # UI
        self.create_widgets()

        # 主循环
        self.update_display()
        self.update_particles()
        master.protocol("WM_DELETE_WINDOW", self.on_closing)

    # ============= UI =============
    def toggle_fullscreen(self, event=None) -> None:
        self.is_fullscreen = not self.is_fullscreen
        self.master.attributes('-fullscreen', self.is_fullscreen)

    def create_widgets(self) -> None:
        main_frame = tk.Frame(self.master, bg=self.bg_color)
        main_frame.place(relx=0.5, rely=0.45, anchor=tk.CENTER)

        tk.Label(main_frame, text="葱称重系统", font=("仿宋", 36, "bold"),
                 bg=self.bg_color, fg='#1e4d1e').pack(pady=(0, 30))

        weight_frame = tk.Frame(main_frame, bg=self.bg_color)
        weight_frame.pack(pady=10)
        tk.Label(weight_frame, text="当前重量", font=("仿宋", 18),
                 bg=self.bg_color, fg='#333').pack()
        self.weight_label = tk.Label(weight_frame, text="0.0 g",
                                      font=("仿宋", 72, "bold"),
                                      bg=self.bg_color, fg='#2d5e2d')
        self.weight_label.pack()

        total_frame = tk.Frame(main_frame, bg=self.bg_color)
        total_frame.pack(pady=30)
        self.total_label = tk.Label(total_frame, text="累计总重: 0.0 g",
                                     font=("仿宋", 22), bg=self.bg_color, fg='#444')
        self.total_label.pack(side=tk.LEFT, padx=20)
        self.clear_btn = tk.Button(total_frame, text="清零总重", command=self.clear_total,
                                    bg='#5a9e5a', fg='white', font=("仿宋", 14, "bold"),
                                    relief=tk.FLAT, padx=20, pady=5, cursor="hand2")
        self.clear_btn.pack(side=tk.LEFT, padx=20)

        # 底部设置区
        settings = tk.Frame(self.master, bg='#e6f0e6', relief=tk.FLAT)
        settings.place(relx=0.5, rely=0.88, anchor=tk.CENTER, width=1100, height=130)

        # 第 1 行：串口设置
        row1 = tk.Frame(settings, bg='#e6f0e6')
        row1.pack(pady=5)
        tk.Label(row1, text="串口号:", bg='#e6f0e6', font=("仿宋", 11)).grid(row=0, column=0, padx=5, pady=5)
        self.port_combo = ttk.Combobox(row1, width=10, font=("仿宋", 10), state='readonly')
        self.port_combo.grid(row=0, column=1, padx=5, pady=5)
        self.refresh_ports()
        tk.Button(row1, text="刷新", command=self.refresh_ports, bg='#a8d5a8',
                  font=("仿宋", 10), relief=tk.FLAT, cursor="hand2").grid(row=0, column=2, padx=5, pady=5)

        tk.Label(row1, text="波特率:", bg='#e6f0e6', font=("仿宋", 11)).grid(row=0, column=3, padx=5, pady=5)
        self.baud_combo = ttk.Combobox(row1, values=['2400', '4800', '9600', '19200', '28800',
                                                       '38400', '57600', '115200'],
                                        width=10, font=("仿宋", 10), state='readonly')
        self.baud_combo.set(str(config.SERIAL_BAUDRATE))
        self.baud_combo.grid(row=0, column=4, padx=5, pady=5)

        self.connect_btn = tk.Button(row1, text="连接", command=self.toggle_connection,
                                      bg='#5a9e5a', fg='white', font=("仿宋", 11, "bold"),
                                      width=8, relief=tk.FLAT, cursor="hand2")
        self.connect_btn.grid(row=0, column=5, padx=15, pady=5)

        self.status_label = tk.Label(row1, text="未连接", bg='#e6f0e6', fg='#a94442',
                                      font=("仿宋", 11))
        self.status_label.grid(row=0, column=6, padx=5, pady=5)

        # 第 2 行：校准按钮
        row2 = tk.Frame(settings, bg='#e6f0e6')
        row2.pack(pady=5)
        tk.Label(row2, text="校准:", bg='#e6f0e6', font=("仿宋", 11)).grid(row=0, column=0, padx=5)
        self.zero_btn = tk.Button(row2, text="零点校准", command=self.do_zero_calibrate,
                                    bg='#7ab07a', fg='white', font=("仿宋", 10, "bold"),
                                    relief=tk.FLAT, padx=10, pady=3, cursor="hand2", state=tk.DISABLED)
        self.zero_btn.grid(row=0, column=1, padx=5)
        self.weight_cal_btn = tk.Button(row2, text="砝码校准", command=self.do_weight_calibrate,
                                          bg='#7ab07a', fg='white', font=("仿宋", 10, "bold"),
                                          relief=tk.FLAT, padx=10, pady=3, cursor="hand2", state=tk.DISABLED)
        self.weight_cal_btn.grid(row=0, column=2, padx=5)
        self.tare_btn = tk.Button(row2, text="去皮", command=self.do_tare,
                                    bg='#7ab07a', fg='white', font=("仿宋", 10, "bold"),
                                    relief=tk.FLAT, padx=10, pady=3, cursor="hand2", state=tk.DISABLED)
        self.tare_btn.grid(row=0, column=3, padx=5)
        self.untare_btn = tk.Button(row2, text="取消去皮", command=self.do_untare,
                                      bg='#7ab07a', fg='white', font=("仿宋", 10, "bold"),
                                      relief=tk.FLAT, padx=10, pady=3, cursor="hand2", state=tk.DISABLED)
        self.untare_btn.grid(row=0, column=4, padx=5)

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

        # 启动自动发送模式
        try:
            self.driver.start_auto_send(mode=1)
        except Exception:
            pass

        # 初始化
        self.connected = True
        self.received_data = False
        self.filter.reset()
        self.stable_judge.reset()
        self.accumulator.clear_total()
        self.last_raw_grams = 0.0
        self.last_filtered_grams = 0.0
        self.last_display_grams = 0.0

        # 模拟器也有 Calibrator 包装
        self.calibrator = Calibrator(self.driver)

        # UI 更新
        self.connect_btn.config(text="断开", bg='#b34b4b')
        for btn in (self.zero_btn, self.weight_cal_btn, self.tare_btn, self.untare_btn):
            btn.config(state=tk.NORMAL)
        if self.is_simulate:
            self.status_label.config(text="虚拟测试模式", fg='#2d5e2d')
        else:
            self.status_label.config(text="已连接", fg='#2d5e2d')

        # 自动零点校准
        if config.AUTO_ZERO_CALIBRATE_ON_CONNECT and not self.is_simulate:
            self._auto_zero_calibrate_flow()
        elif self.is_simulate:
            # 模拟器中也走一遍同样的倒计时流程，便于测试
            self._auto_zero_calibrate_flow()

    def _auto_zero_calibrate_flow(self) -> None:
        """连接后自动零点校准流程（可取消）。"""
        dlg = CountdownDialog(
            self.master,
            title="自动零点校准",
            message="请确认托盘已清空。\n程序将在倒计时结束后自动校准零点。",
            seconds=config.AUTO_CAL_COUNTDOWN_SECONDS,
        )
        self.master.wait_window(dlg)
        if dlg.cancelled:
            self.status_label.config(text=("虚拟测试模式" if self.is_simulate else "已连接（未校准）"),
                                       fg='#a97a2d')
            return
        if self.calibrator is None:
            return
        self.status_label.config(text="零点校准中...", fg='#a97a2d')
        self.master.update()
        ok = self.calibrator.zero_calibrate()
        if ok:
            self.status_label.config(text=("虚拟测试模式" if self.is_simulate else "已连接 · 已自动零点校准"),
                                       fg='#2d5e2d')
        else:
            self.status_label.config(text=("虚拟测试模式" if self.is_simulate else "已连接（校准失败）"),
                                       fg='#a94442')
            messagebox.showwarning("校准失败", "自动零点校准未成功，请手动点击'零点校准'重试。")

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
        self.connect_btn.config(text="连接", bg='#5a9e5a')
        self.status_label.config(text="未连接", fg='#a94442')
        for btn in (self.zero_btn, self.weight_cal_btn, self.tare_btn, self.untare_btn):
            btn.config(state=tk.DISABLED)

    # ============= 校准操作 =============
    def _ensure_connected(self) -> bool:
        if not self.connected or self.calibrator is None:
            messagebox.showinfo("提示", "请先连接电子秤")
            return False
        return True

    def do_zero_calibrate(self) -> None:
        if not self._ensure_connected():
            return
        if not messagebox.askyesno("零点校准", "请确认托盘已清空。\n是否继续？"):
            return
        self.status_label.config(text="零点校准中...", fg='#a97a2d')
        self.master.update()
        ok = self.calibrator.zero_calibrate()
        if ok:
            self.status_label.config(text=("虚拟测试模式" if self.is_simulate else "已连接 · 零点已校准"),
                                       fg='#2d5e2d')
            messagebox.showinfo("完成", "零点校准完成")
        else:
            self.status_label.config(text="校准失败", fg='#a94442')
            messagebox.showerror("失败", "零点校准失败，请检查连接")

    def do_weight_calibrate(self) -> None:
        if not self._ensure_connected():
            return
        warn = ("砝码校准会改变电子秤内部校准参数。\n"
                "请确保已有标准砝码（建议 ≥ 200g）。\n"
                "如首次使用无砝码，请忽略此功能。\n\n"
                "请输入砝码实际重量（克）：")
        val = simpledialog.askfloat("砝码校准", warn,
                                      initialvalue=config.CAL_WEIGHT_GRAMS,
                                      minvalue=1.0, maxvalue=2000.0)
        if val is None:
            return
        weight_ticks = int(round(val / config.GRAMS_PER_TICK))
        self.status_label.config(text="砝码校准中...", fg='#a97a2d')
        self.master.update()
        ok = self.calibrator.weight_calibrate(weight_ticks)
        if ok:
            self.status_label.config(text=f"已校准 {val:.1f}g", fg='#2d5e2d')
            messagebox.showinfo("完成", f"砝码校准完成（{val:.1f} g）\n请取下砝码")
        else:
            self.status_label.config(text="校准失败", fg='#a94442')
            messagebox.showerror("失败", "砝码校准失败，请检查连接")

    def do_tare(self) -> None:
        if not self._ensure_connected():
            return
        if self.calibrator.tare():
            self.status_label.config(text=("虚拟测试模式" if self.is_simulate else "已去皮"), fg='#2d5e2d')
        else:
            messagebox.showerror("失败", "去皮失败")

    def do_untare(self) -> None:
        if not self._ensure_connected():
            return
        if self.calibrator.untare():
            self.status_label.config(text=("虚拟测试模式" if self.is_simulate else "已取消去皮"), fg='#2d5e2d')
        else:
            messagebox.showerror("失败", "取消去皮失败")

    # ============= 业务循环 =============
    def update_particles(self) -> None:
        for p in self.particles:
            p.move()
        self.master.after(30, self.update_particles)

    def update_display(self) -> None:
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
                self.accumulator.update(filtered)
                # 稳定判定
                _, display_val = self.stable_judge.update(filtered)
                self.last_display_grams = max(0.0, display_val)

        # 强制刷新显示
        self.weight_label.config(text=f"{self.last_display_grams:.1f} g")
        self.total_label.config(text=f"累计总重: {self.accumulator.total_weight:.1f} g")

        self.master.after(config.UI_UPDATE_INTERVAL, self.update_display)

    def clear_total(self) -> None:
        if self.connected and self.received_data:
            self.accumulator.clear_total()
            self.total_label.config(text=f"累计总重: {self.accumulator.total_weight:.1f} g")
        else:
            messagebox.showinfo("提示", "未连接设备或无有效数据，无法清零")

    def on_closing(self) -> None:
        if self.driver is not None:
            try:
                self.driver.close()
            except Exception:
                pass
        self.master.destroy()
