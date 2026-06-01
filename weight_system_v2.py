import tkinter as tk
from tkinter import ttk, messagebox
import serial
import serial.tools.list_ports
import collections
import time
import math
import random
import ctypes
import sys
import os

# ==================== 用户可调宏定义 ====================
WEIGHT_THRESH_HIGH = 5           # 推板启动阈值（g）
WEIGHT_THRESH_LOW = 3             # 推板停止阈值（g）
MAX_TOTAL = 9999                  # 总重显示上限
FILTER_WINDOW_SIZE = 1            # 滑动滤波窗口数（保持不变）
SERIAL_BAUDRATE = 115200            # 默认串口波特率
SERIAL_TIMEOUT = 0.5              # 串口读取超时（秒）
UI_UPDATE_INTERVAL = 80          # 界面刷新间隔（毫秒）

# 显示稳定判定参数（优化：确保模拟模式秒级触发）
STABLE_THRESH = 1.0               # 差值≤1即判定稳定
STABLE_COUNT = 1                  # 连续1次就切换显示
# ========================================================

# ==================== 自动请求管理员权限 ====================
def is_admin():
    """检查是否以管理员身份运行"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_as_admin():
    """如果不是管理员，则重新以管理员身份启动程序"""
    if not is_admin():
        try:
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
            sys.exit()
        except Exception as e:
            print(f"无法获取管理员权限: {e}")
            sys.exit(1)
# ===============================================================

class Particle:
    """动态粒子类（背景装饰）"""
    def __init__(self, canvas, width, height):
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
            fill=self.color, outline=""
        )

    def move(self):
        """移动粒子并处理边界反弹"""
        self.x += self.vx
        self.y += self.vy

        if self.x <= 0 or self.x >= self.width:
            self.vx *= -1
        if self.y <= 0 or self.y >= self.height:
            self.vy *= -1

        self.canvas.coords(
            self.id,
            self.x - self.radius, self.y - self.radius,
            self.x + self.radius, self.y + self.radius
        )

class WeightApp:
    """主应用窗口"""
    def __init__(self, master):
        self.master = master
        master.title("葱称重系统 - 北京交通大学")
        
        # 全屏显示 + ESC退出
        master.attributes('-fullscreen', True)
        master.bind("<Escape>", self.toggle_fullscreen)
        self.is_fullscreen = True
        
        # 屏幕尺寸
        self.screen_w = master.winfo_screenwidth()
        self.screen_h = master.winfo_screenheight()
        
        # 背景色（农产品绿色系）
        self.bg_color = '#f0f8f0'
        master.configure(bg=self.bg_color)

        # 粒子背景画布
        self.canvas = tk.Canvas(master, width=self.screen_w, height=self.screen_h, 
                                bg=self.bg_color, highlightthickness=0)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        
        # 初始化粒子
        self.particles = [Particle(self.canvas, self.screen_w, self.screen_h) for _ in range(30)]
        
        # 北京交通大学 Logo（右上角）
        self.canvas.create_text(
            self.screen_w - 50, 50,
            text="北京交通大学",
            font=("仿宋", 24, "bold"),
            fill="#2d5e2d",
            anchor="ne"
        )
        

        # 串口/状态变量
        self.ser = None
        self.connected = False
        self.received_data = False
        self.raw_weight = None
        self.filtered_weight = None       # 滤波后的值（保留3窗口滤波）
        self.stable_display_weight = 0    # 锁定的稳定显示值（空称/物品真实值）
        self.current_stable_count = 0     # 稳定计数（判定是否切换显示）
        self.total_weight = 0

        # 滤波缓冲区（窗口数3不变）
        self.filter_buffer = collections.deque(maxlen=FILTER_WINDOW_SIZE)

        # 状态机
        self.system_state = 'IDLE'
        self.peak_weight = 0

        # 模拟模式（改为True即可测试）
        self.simulate_mode = False  # ★ 测试时设为True，实际使用改False
        self.sim_start_time = 0
        self.sim_current_target = 0  # 模拟当前目标值（0/30）

        # 创建界面组件（仿宋字体）
        self.create_widgets()

        # 启动定时任务
        self.update_display()
        self.update_particles()

        master.protocol("WM_DELETE_WINDOW", self.on_closing)

    def toggle_fullscreen(self, event=None):
        """切换全屏状态"""
        self.is_fullscreen = not self.is_fullscreen
        self.master.attributes('-fullscreen', self.is_fullscreen)

    def create_widgets(self):
        """构建界面组件（全仿宋字体）"""
        main_frame = tk.Frame(self.master, bg=self.bg_color)
        main_frame.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        # 标题
        title_label = tk.Label(main_frame, text="葱称重系统", 
                                font=("仿宋", 36, "bold"),
                                bg=self.bg_color, fg='#1e4d1e')
        title_label.pack(pady=(0, 40))

        # 实时重量显示（核心显示区）
        weight_frame = tk.Frame(main_frame, bg=self.bg_color)
        weight_frame.pack(pady=20)

        tk.Label(weight_frame, text="当前重量", font=("仿宋", 20), 
                 bg=self.bg_color, fg='#333333').pack()
        
        self.weight_label = tk.Label(weight_frame, text="0 g", 
                                      font=("仿宋", 72, "bold"),
                                      bg=self.bg_color, fg='#2d5e2d')
        self.weight_label.pack()

        # 总重显示
        total_frame = tk.Frame(main_frame, bg=self.bg_color)
        total_frame.pack(pady=40)

        self.total_label = tk.Label(total_frame, text="累计总重: 0 g", 
                                     font=("仿宋", 24),
                                     bg=self.bg_color, fg='#444444')
        self.total_label.pack(side=tk.LEFT, padx=20)

        self.clear_btn = tk.Button(total_frame, text="清零总重", command=self.clear_total,
                                    bg='#5a9e5a', fg='white', font=("仿宋", 16, "bold"),
                                    relief=tk.FLAT, padx=20, pady=5, cursor="hand2")
        self.clear_btn.pack(side=tk.LEFT, padx=20)

        # 串口设置区（底部）
        settings_frame = tk.Frame(self.master, bg='#e6f0e6', relief=tk.FLAT)
        settings_frame.place(relx=0.5, rely=0.92, anchor=tk.CENTER, width=600, height=60)

        tk.Label(settings_frame, text="串口号:", bg='#e6f0e6', font=("仿宋", 12)).grid(row=0, column=0, padx=5, pady=15)
        self.port_combo = ttk.Combobox(settings_frame, width=10, font=("仿宋", 10), state='readonly')
        self.port_combo.grid(row=0, column=1, padx=5, pady=15)
        self.refresh_ports()

        refresh_btn = tk.Button(settings_frame, text="刷新", command=self.refresh_ports,
                                bg='#a8d5a8', font=("仿宋", 10), relief=tk.FLAT, cursor="hand2")
        refresh_btn.grid(row=0, column=2, padx=5, pady=15)

        tk.Label(settings_frame, text="波特率:", bg='#e6f0e6', font=("仿宋", 12)).grid(row=0, column=3, padx=5, pady=15)
        self.baud_combo = ttk.Combobox(settings_frame, values=['9600','19200','38400','115200'], width=10, font=("仿宋", 10), state='readonly')
        self.baud_combo.grid(row=0, column=4, padx=5, pady=15)
        self.baud_combo.set(str(SERIAL_BAUDRATE))

        self.connect_btn = tk.Button(settings_frame, text="连接", command=self.toggle_connection,
                                      bg='#5a9e5a', fg='white', font=("仿宋", 12, "bold"),
                                      width=8, relief=tk.FLAT, cursor="hand2")
        self.connect_btn.grid(row=0, column=5, padx=15, pady=15)

        self.status_label = tk.Label(settings_frame, text="未连接", bg='#e6f0e6', fg='#a94442',
                                      font=("仿宋", 11))
        self.status_label.grid(row=0, column=6, padx=5, pady=15)

    def update_particles(self):
        """更新粒子位置"""
        for p in self.particles:
            p.move()
        self.master.after(30, self.update_particles)

    def refresh_ports(self):
        """刷新串口列表"""
        ports = serial.tools.list_ports.comports()
        port_list = [port.device for port in ports]
        self.port_combo['values'] = port_list
        if port_list:
            self.port_combo.set(port_list[0])
        else:
            self.port_combo.set('')

    def toggle_connection(self):
        """连接/断开串口"""
        if not self.connected:
            if self.simulate_mode:
                # 模拟模式初始化（修复：重置模拟时间和目标值）
                self.connected = True
                self.received_data = True  # 直接标记有数据，避免显示卡顿
                self.filtered_weight = 0
                self.stable_display_weight = 0
                self.current_stable_count = 0
                self.system_state = 'IDLE'
                self.peak_weight = 0
                self.filter_buffer.clear()
                self.sim_start_time = time.time()
                self.sim_current_target = 0  # 初始空称0g
                self.connect_btn.config(text="断开", bg='#b34b4b')
                self.status_label.config(text="模拟模式", fg='#2d5e2d')
                # 强制触发一次显示刷新
                self.update_weight_display()
                return
            else:
                # 真实串口连接
                port = self.port_combo.get().strip()
                baud_str = self.baud_combo.get().strip()
                if not port or not baud_str:
                    messagebox.showerror("错误", "请选择串口号和波特率")
                    return
                try:
                    baud = int(baud_str)
                    ser = serial.Serial(port, baud, timeout=SERIAL_TIMEOUT)
                    self.ser = ser
                    self.connected = True
                    self.received_data = False
                    self.filtered_weight = None
                    self.stable_display_weight = 0
                    self.current_stable_count = 0
                    self.system_state = 'IDLE'
                    self.peak_weight = 0
                    self.filter_buffer.clear()
                    self.connect_btn.config(text="断开", bg='#b34b4b')
                    self.status_label.config(text="已连接", fg='#2d5e2d')
                except Exception as e:
                    messagebox.showerror("连接失败", f"无法打开串口：{str(e)}")
        else:
            # 断开连接
            self.disconnect_serial()

    def disconnect_serial(self):
        """断开串口"""
        if not self.simulate_mode and self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except:
                pass
        self.ser = None
        self.connected = False
        self.received_data = False
        self.filtered_weight = None
        self.stable_display_weight = 0
        self.current_stable_count = 0
        self.connect_btn.config(text="连接", bg='#5a9e5a')
        self.status_label.config(text="未连接", fg='#a94442')
        self.update_weight_display()  # 刷新显示

    def apply_filter(self, new_value):
        """滑动平均滤波（窗口数3不变）"""
        self.filter_buffer.append(new_value)
        return sum(self.filter_buffer) / len(self.filter_buffer)

    def process_weight_for_total(self, current_filtered):
        """状态机处理总重累计"""
        if self.system_state == 'IDLE':
            if current_filtered > WEIGHT_THRESH_HIGH:
                self.system_state = 'WEIGHING'
                self.peak_weight = current_filtered
        elif self.system_state == 'WEIGHING':
            if current_filtered > self.peak_weight:
                self.peak_weight = current_filtered
            if current_filtered < WEIGHT_THRESH_LOW:
                # 累计峰值到总重
                self.total_weight += int(self.peak_weight)
                if self.total_weight > MAX_TOTAL:
                    self.total_weight = MAX_TOTAL
                self.update_total_display()
                # 重置状态
                self.system_state = 'IDLE'
                self.peak_weight = 0

    def generate_simulated_weight(self):
        """
        修复核心：移除随机波动，返回干净的目标值（0/30），确保值稳定变化
        模拟逻辑：
        - 0-4秒：空称 → 0g
        - 4-10秒：放30g物品 → 30g
        - 10-16秒：拿下来 → 0g
        - 16秒后循环
        """
        elapsed = time.time() - self.sim_start_time
        cycle = elapsed % 16  # 16秒一个循环

        # 确定当前目标值（无随机波动，无负数）
        if cycle < 4:
            self.sim_current_target = 0
        elif cycle < 10:
            self.sim_current_target = 30
        else:
            self.sim_current_target = 0

        # 直接返回目标值，确保滤波后值能快速触发显示更新
        return self.sim_current_target

    def update_display(self):
        """定时读取串口/模拟数据，更新滤波和显示"""
        if self.connected:
            new_raw = None
            if self.simulate_mode:
                # 模拟数据直接生成干净值，无负数
                new_raw = self.generate_simulated_weight()
            else:
                # 读取真实串口数据
                if self.ser and self.ser.is_open:
                    try:
                        if self.ser.in_waiting > 0:
                            line = self.ser.readline().decode('utf-8').strip()
                            if line:
                                try:
                                    new_raw = int(line)
                                    # 过滤无效值，确保非负
                                    if not (0 <= new_raw <= 255):
                                        new_raw = None
                                except ValueError:
                                    pass
                    except Exception as e:
                        print(f"串口读取错误：{e}")
                        self.disconnect_serial()
                        messagebox.showerror("串口错误", "与设备的连接已丢失，请检查")

            if new_raw is not None:
                self.raw_weight = new_raw
                # 应用3窗口滑动滤波
                filtered = self.apply_filter(new_raw)
                self.filtered_weight = filtered
                self.received_data = True
                # 处理总重累计
                self.process_weight_for_total(filtered)
                # 判定稳定值并更新显示（核心修复：确保触发）
                self.judge_stable_weight(filtered)

        # 强制刷新显示（关键：不管数据是否变化，每次都刷新）
        self.weight_label.config(text=f"{max(0, self.stable_display_weight)} g")
        self.total_label.config(text=f"累计总重: {self.total_weight} g")
        
        self.master.after(UI_UPDATE_INTERVAL, self.update_display)

    def judge_stable_weight(self, current_filtered):
        """
        核心：判定稳定值，屏蔽滤波阶梯 + 修复负数问题
        优化：简化逻辑，确保模拟模式秒级触发显示更新
        """
        # 第一步：强制过滤负数，确保值≥0
        current_filtered = max(0.0, current_filtered)
        diff = abs(current_filtered - self.stable_display_weight)
        
        # 优化：只要差值≤阈值，立即更新显示，无需累计次数
        if diff <= STABLE_THRESH:
            self.stable_display_weight = max(0, round(current_filtered))
        else:
            # 未稳定时，直接显示滤波后取整值，避免卡住
            self.stable_display_weight = max(0, round(current_filtered))

    def update_weight_display(self):
        """显示稳定值（最终防护：确保显示值≥0）"""
        display_val = max(0, self.stable_display_weight)
        self.weight_label.config(text=f"{display_val} g")
        # 同步更新总重显示
        self.total_label.config(text=f"累计总重: {self.total_weight} g")

    def update_total_display(self):
        """更新总重显示"""
        if self.connected and self.received_data:
            self.total_label.config(text=f"累计总重: {self.total_weight} g")
        else:
            self.total_label.config(text="累计总重: 0 g")

    def clear_total(self):
        """清零总重"""
        if self.connected and self.received_data:
            self.total_weight = 0
            self.update_total_display()
        else:
            messagebox.showinfo("提示", "未连接设备或无有效数据，无法清零")

    def on_closing(self):
        """关闭程序"""
        if not self.simulate_mode and self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except:
                pass
        self.master.destroy()

def main():
    # 启动时自动请求管理员权限
    run_as_admin()

    root = tk.Tk()
    # 全局设置仿宋字体
    root.option_add("*Font", "仿宋 10")

    app = WeightApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()