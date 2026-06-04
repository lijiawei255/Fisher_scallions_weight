#!/usr/bin/env python3
"""
生成 README 中嵌入的 SVG 插图。
运行: python generate_diagrams.py
产物: images/*.svg
"""

import os

IMAGES_DIR = os.path.join(os.path.dirname(__file__), "images")
os.makedirs(IMAGES_DIR, exist_ok=True)

GREEN = "#16a34a"
GREEN_LIGHT = "#dcfce7"
GREEN_MID = "#86efac"
BLUE = "#0ea5e9"
BLUE_LIGHT = "#e0f2fe"
RED = "#dc2626"
RED_LIGHT = "#fee2e2"
GRAY_100 = "#f4f6fa"
GRAY_200 = "#e2e8f0"
GRAY_400 = "#94a3b8"
GRAY_500 = "#64748b"
GRAY_700 = "#475569"
GRAY_900 = "#0f172a"
WHITE = "#ffffff"
ORANGE = "#f59e0b"
ORANGE_LIGHT = "#fef3c7"


def write_svg(name: str, w: int, h: int, content: str) -> str:
    path = os.path.join(IMAGES_DIR, f"{name}.svg")
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        f'width="{w}" height="{h}">\n'
        f'  <rect width="{w}" height="{h}" fill="{WHITE}" rx="12"/>\n'
        f'{content}\n</svg>\n'
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    return path


# ============================================================
# 图 1: 整体数据流架构图
# ============================================================
write_svg(
    "architecture", 800, 260,
    f"""
  <!-- 标题 -->
  <text x="400" y="36" text-anchor="middle" font-family="Microsoft YaHei, sans-serif"
        font-size="18" font-weight="bold" fill="{GRAY_900}">数据处理流水线</text>

  <!-- 电子秤 -->
  <rect x="40" y="80" width="130" height="80" rx="12" fill="{GREEN_LIGHT}" stroke="{GREEN}" stroke-width="2"/>
  <text x="105" y="110" text-anchor="middle" font-family="Microsoft YaHei" font-size="14" font-weight="bold" fill="{GREEN}">电子秤</text>
  <text x="105" y="132" text-anchor="middle" font-family="Microsoft YaHei" font-size="12" fill="{GRAY_700}">CMCU-07</text>
  <text x="105" y="150" text-anchor="middle" font-family="Consolas, monospace" font-size="11" fill="{GRAY_500}">100ms 自动发送</text>

  <!-- 协议解析 -->
  <rect x="230" y="80" width="130" height="80" rx="12" fill="{BLUE_LIGHT}" stroke="{BLUE}" stroke-width="2"/>
  <text x="295" y="110" text-anchor="middle" font-family="Microsoft YaHei" font-size="14" font-weight="bold" fill="{BLUE}">协议解析</text>
  <text x="295" y="132" text-anchor="middle" font-family="Microsoft YaHei" font-size="12" fill="{GRAY_700}">scale_protocol</text>
  <text x="295" y="150" text-anchor="middle" font-family="Consolas, monospace" font-size="11" fill="{GRAY_500}">10字节帧校验</text>

  <!-- 稳定判定 -->
  <rect x="420" y="80" width="130" height="80" rx="12" fill="{GREEN_LIGHT}" stroke="{GREEN}" stroke-width="2"/>
  <text x="485" y="110" text-anchor="middle" font-family="Microsoft YaHei" font-size="14" font-weight="bold" fill="{GREEN}">稳定判定</text>
  <text x="485" y="132" text-anchor="middle" font-family="Microsoft YaHei" font-size="12" fill="{GRAY_700}">weight_filter</text>
  <text x="485" y="150" text-anchor="middle" font-family="Consolas, monospace" font-size="11" fill="{GRAY_500}">连续N次波动&lt;阈值</text>

  <!-- 状态机 -->
  <rect x="610" y="80" width="130" height="80" rx="12" fill="{ORANGE_LIGHT}" stroke="{ORANGE}" stroke-width="2"/>
  <text x="675" y="110" text-anchor="middle" font-family="Microsoft YaHei" font-size="14" font-weight="bold" fill="#b45309">业务状态机</text>
  <text x="675" y="132" text-anchor="middle" font-family="Microsoft YaHei" font-size="12" fill="{GRAY_700}">weight_state</text>
  <text x="675" y="150" text-anchor="middle" font-family="Consolas, monospace" font-size="11" fill="{GRAY_500}">IDLE ↔ WEIGHING</text>

  <!-- 箭头 1→2 -->
  <line x1="170" y1="120" x2="225" y2="120" stroke="{GRAY_400}" stroke-width="2" marker-end="url(#arrow)"/>
  <text x="197" y="110" text-anchor="middle" font-family="Microsoft YaHei" font-size="10" fill="{GRAY_500}">串口原始字节</text>

  <!-- 箭头 2→3 -->
  <line x1="360" y1="120" x2="415" y2="120" stroke="{GRAY_400}" stroke-width="2" marker-end="url(#arrow)"/>
  <text x="387" y="110" text-anchor="middle" font-family="Microsoft YaHei" font-size="10" fill="{GRAY_500}">重量克数</text>

  <!-- 箭头 3→4 -->
  <line x1="550" y1="120" x2="605" y2="120" stroke="{GRAY_400}" stroke-width="2" marker-end="url(#arrow)"/>
  <text x="577" y="110" text-anchor="middle" font-family="Microsoft YaHei" font-size="10" fill="{GRAY_500}">稳定克数</text>

  <!-- 底部 UI 输出 -->
  <rect x="310" y="200" width="180" height="44" rx="22" fill="{GREEN}" stroke="{GREEN}" stroke-width="2"/>
  <text x="400" y="228" text-anchor="middle" font-family="Microsoft YaHei" font-size="15" font-weight="bold" fill="{WHITE}">UI 显示（大字）</text>

  <line x1="485" y1="160" x2="400" y2="200" stroke="{GRAY_400}" stroke-width="2" stroke-dasharray="4,3" marker-end="url(#arrow)"/>

  <rect x="610" y="200" width="130" height="44" rx="22" fill="#b45309"/>
  <text x="675" y="228" text-anchor="middle" font-family="Microsoft YaHei" font-size="14" font-weight="bold" fill="{WHITE}">累计总重 + N</text>

  <line x1="675" y1="160" x2="675" y2="198" stroke="{GRAY_400}" stroke-width="2" marker-end="url(#arrow)"/>

  <!-- 箭头标记 -->
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5"
            markerWidth="6" markerHeight="6" orient="auto">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="{GRAY_400}"/>
    </marker>
  </defs>
"""
)

# ============================================================
# 图 2: 推板下压数据锁定原理
# ============================================================
write_svg(
    "data_locking", 820, 340,
    f"""
  <text x="410" y="36" text-anchor="middle" font-family="Microsoft YaHei, sans-serif"
        font-size="18" font-weight="bold" fill="{GRAY_900}">推板下压干扰 → 数据锁定原理</text>

  <!-- 坐标轴 -->
  <line x1="100" y1="280" x2="760" y2="280" stroke="{GRAY_500}" stroke-width="2"/>
  <line x1="100" y1="60" x2="100" y2="280" stroke="{GRAY_500}" stroke-width="2"/>
  <text x="50" y="170" text-anchor="middle" font-family="Microsoft YaHei" font-size="13" fill="{GRAY_700}">重量 (g)</text>
  <text x="755" y="275" text-anchor="end" font-family="Microsoft YaHei" font-size="13" fill="{GRAY_700}">时间 →</text>

  <!-- 刻度线 -->
  <line x1="95" y1="240" x2="100" y2="240" stroke="{GRAY_500}" stroke-width="1"/>
  <text x="88" y="244" text-anchor="end" font-family="Microsoft YaHei" font-size="11" fill="{GRAY_500}">0</text>
  <line x1="95" y1="180" x2="100" y2="180" stroke="{GRAY_500}" stroke-width="1"/>
  <text x="88" y="184" text-anchor="end" font-family="Microsoft YaHei" font-size="11" fill="{GRAY_500}">30</text>

  <!-- 物品放上台阶段 -->
  <line x1="140" y1="240" x2="220" y2="240" stroke="{BLUE}" stroke-width="3"/>
  <line x1="220" y1="240" x2="260" y2="180" stroke="{BLUE}" stroke-width="3"/>

  <!-- 稳定区（绿色阴影） -->
  <rect x="260" y="170" width="100" height="20" rx="4" fill="{GREEN_LIGHT}" opacity="0.7"/>
  <text x="310" y="162" text-anchor="middle" font-family="Microsoft YaHei" font-size="12" font-weight="bold" fill="{GREEN}">稳定 = 30g</text>
  <line x1="260" y1="180" x2="360" y2="180" stroke="{GREEN}" stroke-width="3"/>

  <!-- 数据锁定标记 -->
  <rect x="260" y="166" width="100" height="2" fill="{GREEN}" stroke-dasharray="2,2"/>
  <text x="310" y="205" text-anchor="middle" font-family="Microsoft YaHei" font-size="12" fill="{GREEN}">🔒 锁定重量 = 30g</text>

  <!-- 推板下压阶段（红色上升） -->
  <line x1="360" y1="180" x2="400" y2="155" stroke="{RED}" stroke-width="3"/>
  <line x1="400" y1="155" x2="440" y2="150" stroke="{RED}" stroke-width="3"/>
  <rect x="360" y="140" width="100" height="22" rx="4" fill="{RED_LIGHT}" opacity="0.8"/>
  <text x="410" y="155" text-anchor="middle" font-family="Microsoft YaHei" font-size="11" font-weight="bold" fill="{RED}">推板下压！</text>

  <!-- 锁定后的水平线（绿色，不受推板影响） -->
  <line x1="360" y1="195" x2="500" y2="195" stroke="{GREEN}" stroke-width="2" stroke-dasharray="6,4"/>
  <text x="430" y="192" text-anchor="middle" font-family="Microsoft YaHei" font-size="11" fill="{GREEN}">显示值保持 30g 不变</text>

  <!-- 物品被推走，重量下降 -->
  <line x1="440" y1="150" x2="480" y2="240" stroke="{BLUE}" stroke-width="3"/>
  <line x1="480" y1="240" x2="600" y2="240" stroke="{BLUE}" stroke-width="3"/>

  <!-- 累计事件标记 -->
  <circle cx="490" cy="250" r="20" fill="{ORANGE_LIGHT}" stroke="{ORANGE}" stroke-width="2"/>
  <text x="490" y="254" text-anchor="middle" font-family="Microsoft YaHei" font-size="10" font-weight="bold" fill="#b45309">累计</text>
  <text x="550" y="254" text-anchor="start" font-family="Microsoft YaHei" font-size="12" fill="#b45309">总重 += 30g ✓</text>

  <!-- 阶段标注 -->
  <text x="180" y="265" text-anchor="middle" font-family="Microsoft YaHei" font-size="11" fill="{GRAY_700}">①放上</text>
  <text x="310" y="265" text-anchor="middle" font-family="Microsoft YaHei" font-size="11" fill="{GREEN}">②稳定锁定</text>
  <text x="410" y="265" text-anchor="middle" font-family="Microsoft YaHei" font-size="11" fill="{RED}">③推板干扰</text>
  <text x="540" y="265" text-anchor="middle" font-family="Microsoft YaHei" font-size="11" fill="{BLUE}">④推走累计</text>

  <!-- 底部关键说明 -->
  <rect x="100" y="295" width="620" height="32" rx="8" fill="{GREEN_LIGHT}" stroke="{GREEN}" stroke-width="1"/>
  <text x="410" y="316" text-anchor="middle" font-family="Microsoft YaHei" font-size="13" font-weight="bold" fill="{GREEN}">核心策略：重量稳定后立即锁定，之后推板下压导致的升高值一律忽略，直到物品离开才累计锁定值</text>
"""
)

# ============================================================
# 图 3: 状态机流转图
# ============================================================
write_svg(
    "state_machine", 700, 300,
    f"""
  <text x="350" y="36" text-anchor="middle" font-family="Microsoft YaHei, sans-serif"
        font-size="18" font-weight="bold" fill="{GRAY_900}">称重业务状态机</text>

  <!-- IDLE 状态 -->
  <rect x="60" y="100" width="160" height="80" rx="40" fill="{GRAY_200}" stroke="{GRAY_500}" stroke-width="2"/>
  <text x="140" y="140" text-anchor="middle" font-family="Microsoft YaHei" font-size="20" font-weight="bold" fill="{GRAY_700}">IDLE</text>
  <text x="140" y="162" text-anchor="middle" font-family="Microsoft YaHei" font-size="12" fill="{GRAY_500}">空闲等待</text>

  <!-- WEIGHING 状态 -->
  <rect x="460" y="100" width="180" height="80" rx="40" fill="{GREEN_LIGHT}" stroke="{GREEN}" stroke-width="2"/>
  <text x="550" y="136" text-anchor="middle" font-family="Microsoft YaHei" font-size="16" font-weight="bold" fill="{GREEN}">WEIGHING</text>
  <text x="550" y="158" text-anchor="middle" font-family="Microsoft YaHei" font-size="12" fill="{GRAY_700}">称重中 · 锁定重量</text>

  <!-- IDLE → WEIGHING 箭头 -->
  <line x1="220" y1="140" x2="455" y2="140" stroke="{GREEN}" stroke-width="2" marker-end="url(#arrow-g)"/>
  <rect x="228" y="105" width="216" height="32" rx="6" fill="{GREEN}" opacity="0.08"/>
  <text x="340" y="126" text-anchor="middle" font-family="Microsoft YaHei" font-size="12" font-weight="bold" fill="{GREEN}">连续 2 次重量 &gt; 2g（进入）</text>

  <!-- WEIGHING → IDLE 箭头（下方） -->
  <path d="M 550 180 Q 550 250 340 250 Q 140 250 140 182" fill="none"
        stroke="{BLUE}" stroke-width="2" marker-end="url(#arrow-b)"/>
  <rect x="240" y="225" width="200" height="32" rx="6" fill="{BLUE_LIGHT}" stroke="{BLUE}" stroke-width="1"/>
  <text x="340" y="246" text-anchor="middle" font-family="Microsoft YaHei" font-size="12" font-weight="bold" fill="{BLUE}">连续 1 次重量 &lt; 2g（退出累计）</text>

  <!-- 循环内的锁定说明 -->
  <rect x="480" y="185" width="140" height="30" rx="8" fill="{GREEN}" opacity="0.12"/>
  <text x="550" y="205" text-anchor="middle" font-family="Microsoft YaHei" font-size="11" fill="{GREEN}">首次稳定即锁定</text>

  <!-- 箭头标记 -->
  <defs>
    <marker id="arrow-g" viewBox="0 0 10 10" refX="9" refY="5"
            markerWidth="6" markerHeight="6" orient="auto">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="{GREEN}"/>
    </marker>
    <marker id="arrow-b" viewBox="0 0 10 10" refX="9" refY="5"
            markerWidth="6" markerHeight="6" orient="auto">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="{BLUE}"/>
    </marker>
  </defs>
"""
)

# ============================================================
# 图 4: 稳定判定原理（实际行为：硬件已滤波，软件仅延迟1个采样确认）
# ============================================================
write_svg(
    "stable_judge", 800, 280,
    f"""
  <text x="400" y="36" text-anchor="middle" font-family="Microsoft YaHei, sans-serif"
        font-size="18" font-weight="bold" fill="{GRAY_900}">稳定判定：跳变时延迟100ms再更新</text>

  <!-- 坐标轴 -->
  <line x1="100" y1="210" x2="740" y2="210" stroke="{GRAY_500}" stroke-width="2"/>
  <line x1="100" y1="60" x2="100" y2="210" stroke="{GRAY_500}" stroke-width="2"/>
  <text x="50" y="135" text-anchor="middle" font-family="Microsoft YaHei" font-size="13" fill="{GRAY_700}">重量 (g)</text>

  <!-- 刻度 -->
  <line x1="95" y1="190" x2="100" y2="190" stroke="{GRAY_500}"/>
  <text x="88" y="194" text-anchor="end" font-family="Consolas" font-size="11" fill="{GRAY_500}">0</text>
  <line x1="95" y1="110" x2="100" y2="110" stroke="{GRAY_500}"/>
  <text x="88" y="114" text-anchor="end" font-family="Consolas" font-size="11" fill="{GRAY_500}">30</text>

  <!-- 硬件读数（蓝色）：一步跳到 30，干净无抖动 -->
  <line x1="140" y1="190" x2="280" y2="190" stroke="{BLUE}" stroke-width="3"/>
  <line x1="280" y1="190" x2="280" y2="110" stroke="{BLUE}" stroke-width="3"/>
  <line x1="280" y1="110" x2="480" y2="110" stroke="{BLUE}" stroke-width="3"/>
  <text x="200" y="205" text-anchor="middle" font-family="Microsoft YaHei" font-size="11" fill="{BLUE}">硬件：一步跳到30（已滤波）</text>

  <!-- 显示值（绿色）：延迟1个采样(100ms)后跳到30 -->
  <line x1="140" y1="190" x2="340" y2="190" stroke="{GREEN}" stroke-width="3"/>
  <line x1="340" y1="190" x2="340" y2="110" stroke="{GREEN}" stroke-width="3"/>
  <line x1="340" y1="110" x2="480" y2="110" stroke="{GREEN}" stroke-width="3"/>
  <text x="240" y="205" text-anchor="middle" font-family="Microsoft YaHei" font-size="11" fill="{GREEN}">显示：延迟100ms确认 → 跳到30</text>

  <!-- 延迟区间标注 -->
  <rect x="280" y="182" width="60" height="16" rx="4" fill="{ORANGE_LIGHT}" stroke="{ORANGE}" stroke-width="1"/>
  <text x="310" y="194" text-anchor="middle" font-family="Consolas" font-size="9" fill="#b45309">100ms</text>
  <line x1="280" y1="185" x2="280" y2="195" stroke="{ORANGE}" stroke-width="1"/>
  <line x1="340" y1="185" x2="340" y2="195" stroke="{ORANGE}" stroke-width="1"/>

  <!-- 物品离开场景 -->
  <line x1="480" y1="110" x2="520" y2="190" stroke="{BLUE}" stroke-width="3"/>
  <line x1="520" y1="190" x2="660" y2="190" stroke="{BLUE}" stroke-width="3"/>
  <line x1="480" y1="110" x2="480" y2="190" stroke="{GREEN}" stroke-width="3" stroke-dasharray="4,3"/>
  <line x1="480" y1="190" x2="660" y2="190" stroke="{GREEN}" stroke-width="3"/>
  <rect x="460" y="115" width="80" height="22" rx="6" fill="{RED_LIGHT}" stroke="{RED}" stroke-width="1"/>
  <text x="500" y="130" text-anchor="middle" font-family="Microsoft YaHei" font-size="10" font-weight="bold" fill="{RED}">强制归零</text>

  <!-- 说明框 -->
  <rect x="540" y="60" width="220" height="110" rx="10" fill="{GRAY_100}" stroke="{GRAY_200}" stroke-width="1"/>
  <text x="650" y="85" text-anchor="middle" font-family="Microsoft YaHei" font-size="13" font-weight="bold" fill="{GRAY_900}">工作原理</text>
  <text x="560" y="108" font-family="Microsoft YaHei" font-size="11" fill="{GRAY_700}">• 硬件中值+平均滤波，读数干净</text>
  <text x="560" y="126" font-family="Microsoft YaHei" font-size="11" fill="{GRAY_700}">• 跳变时：延迟1个采样(100ms)确认</text>
  <text x="560" y="144" font-family="Microsoft YaHei" font-size="11" fill="{GRAY_700}">• 确认后一步更新，不显示中间值</text>
  <text x="560" y="162" font-family="Microsoft YaHei" font-size="11" fill="{GRAY_700}">• 物品离开：强制归零，不显示下降</text>

  <!-- 底部说明 -->
  <rect x="100" y="225" width="640" height="30" rx="8" fill="{GREEN_LIGHT}" stroke="{GREEN}" stroke-width="1"/>
  <text x="420" y="245" text-anchor="middle" font-family="Microsoft YaHei" font-size="12" font-weight="bold" fill="{GREEN}">效果：数字只有 0 → 30 → 0 三步变化，中间不显示任何抖动或过渡值</text>
"""
)

# ============================================================
# 图 5: 总重累计逻辑
# ============================================================
write_svg(
    "total_weight", 700, 280,
    f"""
  <text x="350" y="36" text-anchor="middle" font-family="Microsoft YaHei, sans-serif"
        font-size="18" font-weight="bold" fill="{GRAY_900}">总重累计逻辑</text>

  <!-- 物品1 -->
  <rect x="60" y="70" width="140" height="160" rx="12" fill="{GREEN_LIGHT}" stroke="{GREEN}" stroke-width="2"/>
  <text x="130" y="100" text-anchor="middle" font-family="Microsoft YaHei" font-size="14" font-weight="bold" fill="{GREEN}">物品 ①</text>
  <text x="130" y="130" text-anchor="middle" font-family="Consolas" font-size="24" font-weight="bold" fill="{GREEN}">30g</text>
  <text x="130" y="155" text-anchor="middle" font-family="Microsoft YaHei" font-size="11" fill="{GRAY_500}">放上→稳定→锁定→推走</text>
  <text x="130" y="175" text-anchor="middle" font-family="Microsoft YaHei" font-size="11" fill="{GRAY_500}">锁定值 = 30g</text>

  <!-- 箭头 -->
  <text x="230" y="150" text-anchor="middle" font-family="Microsoft YaHei" font-size="24" fill="{GREEN}">+</text>

  <!-- 物品2 -->
  <rect x="260" y="70" width="140" height="160" rx="12" fill="{GREEN_LIGHT}" stroke="{GREEN}" stroke-width="2"/>
  <text x="330" y="100" text-anchor="middle" font-family="Microsoft YaHei" font-size="14" font-weight="bold" fill="{GREEN}">物品 ②</text>
  <text x="330" y="130" text-anchor="middle" font-family="Consolas" font-size="24" font-weight="bold" fill="{GREEN}">25g</text>
  <text x="330" y="155" text-anchor="middle" font-family="Microsoft YaHei" font-size="11" fill="{GRAY_500}">放上→稳定→锁定→推走</text>
  <text x="330" y="175" text-anchor="middle" font-family="Microsoft YaHei" font-size="11" fill="{GRAY_500}">锁定值 = 25g</text>

  <!-- 箭头 -->
  <text x="430" y="150" text-anchor="middle" font-family="Microsoft YaHei" font-size="24" fill="{GREEN}">+</text>

  <!-- 物品3 -->
  <rect x="460" y="70" width="140" height="160" rx="12" fill="{GREEN_LIGHT}" stroke="{GREEN}" stroke-width="2"/>
  <text x="530" y="100" text-anchor="middle" font-family="Microsoft YaHei" font-size="14" font-weight="bold" fill="{GREEN}">物品 ③</text>
  <text x="530" y="130" text-anchor="middle" font-family="Consolas" font-size="24" font-weight="bold" fill="{GREEN}">35g</text>
  <text x="530" y="155" text-anchor="middle" font-family="Microsoft YaHei" font-size="11" fill="{GRAY_500}">放上→稳定→锁定→推走</text>
  <text x="530" y="175" text-anchor="middle" font-family="Microsoft YaHei" font-size="11" fill="{GRAY_500}">锁定值 = 35g</text>

  <!-- 结果 -->
  <rect x="100" y="245" width="500" height="28" rx="14" fill="{GREEN}"/>
  <text x="350" y="265" text-anchor="middle" font-family="Microsoft YaHei" font-size="14" font-weight="bold" fill="{WHITE}">累计总重 = 30 + 25 + 35 = 90g</text>
"""
)

# ============================================================
# 图 6: 实时称重处理时序图
# ============================================================
write_svg(
    "weighing_timeline", 820, 340,
    f"""
  <text x="410" y="36" text-anchor="middle" font-family="Microsoft YaHei, sans-serif"
        font-size="18" font-weight="bold" fill="{GRAY_900}">一次完整称重的时间线</text>

  <!-- 时间轴 -->
  <line x1="80" y1="200" x2="760" y2="200" stroke="{GRAY_400}" stroke-width="3" stroke-linecap="round"/>

  <!-- 阶段圆点 -->
  <!-- 阶段1 -->
  <circle cx="130" cy="200" r="16" fill="{BLUE_LIGHT}" stroke="{BLUE}" stroke-width="2"/>
  <text x="130" y="205" text-anchor="middle" font-family="Microsoft YaHei" font-size="12" font-weight="bold" fill="{BLUE}">1</text>
  <text x="130" y="165" text-anchor="middle" font-family="Microsoft YaHei" font-size="12" fill="{BLUE}">托盘空载</text>
  <text x="130" y="235" text-anchor="middle" font-family="Microsoft YaHei" font-size="11" fill="{GRAY_500}">重量 ≈ 0g</text>
  <text x="130" y="250" text-anchor="middle" font-family="Microsoft YaHei" font-size="11" fill="{GRAY_500}">IDLE 状态</text>

  <!-- 阶段2 -->
  <circle cx="280" cy="200" r="16" fill="{GREEN_LIGHT}" stroke="{GREEN}" stroke-width="2"/>
  <text x="280" y="205" text-anchor="middle" font-family="Microsoft YaHei" font-size="12" font-weight="bold" fill="{GREEN}">2</text>
  <text x="280" y="165" text-anchor="middle" font-family="Microsoft YaHei" font-size="12" fill="{GREEN}">放上葱</text>
  <text x="280" y="235" text-anchor="middle" font-family="Microsoft YaHei" font-size="11" fill="{GRAY_500}">重量跳变 &gt; 2g</text>
  <text x="280" y="250" text-anchor="middle" font-family="Microsoft YaHei" font-size="11" fill="{GRAY_500}">进入 WEIGHING</text>

  <!-- 阶段3 -->
  <circle cx="430" cy="200" r="16" fill="{GREEN}" stroke="{GREEN}" stroke-width="2"/>
  <text x="430" y="205" text-anchor="middle" font-family="Microsoft YaHei" font-size="12" font-weight="bold" fill="{WHITE}">3</text>
  <text x="430" y="165" text-anchor="middle" font-family="Microsoft YaHei" font-size="12" fill="{GREEN}">重量稳定</text>
  <text x="430" y="235" text-anchor="middle" font-family="Microsoft YaHei" font-size="11" fill="{GRAY_500}">连续N次波动&lt;阈值</text>
  <text x="430" y="250" text-anchor="middle" font-family="Microsoft YaHei" font-size="11" fill="{GRAY_500}">🔒 锁定重量</text>

  <!-- 阶段4 -->
  <circle cx="580" cy="200" r="16" fill="{RED_LIGHT}" stroke="{RED}" stroke-width="2"/>
  <text x="580" y="205" text-anchor="middle" font-family="Microsoft YaHei" font-size="12" font-weight="bold" fill="{RED}">4</text>
  <text x="580" y="165" text-anchor="middle" font-family="Microsoft YaHei" font-size="12" fill="{RED}">推板推走</text>
  <text x="580" y="235" text-anchor="middle" font-family="Microsoft YaHei" font-size="11" fill="{GRAY_500}">推板可能下压秤盘</text>
  <text x="580" y="250" text-anchor="middle" font-family="Microsoft YaHei" font-size="11" fill="{GRAY_500}">但显示值不变 ✓</text>

  <!-- 阶段5 -->
  <circle cx="720" cy="200" r="16" fill="{ORANGE_LIGHT}" stroke="{ORANGE}" stroke-width="2"/>
  <text x="720" y="205" text-anchor="middle" font-family="Microsoft YaHei" font-size="12" font-weight="bold" fill="#b45309">5</text>
  <text x="720" y="165" text-anchor="middle" font-family="Microsoft YaHei" font-size="12" fill="#b45309">累计总重</text>
  <text x="720" y="235" text-anchor="middle" font-family="Microsoft YaHei" font-size="11" fill="{GRAY_500}">物品离开秤盘</text>
  <text x="720" y="250" text-anchor="middle" font-family="Microsoft YaHei" font-size="11" fill="{GRAY_500}">锁定值加入总重</text>

  <!-- 底部关键说明 -->
  <rect x="80" y="275" width="660" height="50" rx="10" fill="{GREEN_LIGHT}" stroke="{GREEN}" stroke-width="1"/>
  <text x="410" y="297" text-anchor="middle" font-family="Microsoft YaHei" font-size="13" font-weight="bold" fill="{GREEN}">关键：第3步锁定后，第4步推板下压不会影响显示值</text>
  <text x="410" y="317" text-anchor="middle" font-family="Microsoft YaHei" font-size="12" fill="{GREEN}">第5步只用锁定值累计，确保"总重 = 用户看到的所有值之和"</text>
"""
)


# ============================================================
# 图 7: 串口通信协议帧格式
# ============================================================
write_svg(
    "protocol_frame", 780, 220,
    f"""
  <text x="390" y="36" text-anchor="middle" font-family="Microsoft YaHei, sans-serif"
        font-size="18" font-weight="bold" fill="{GRAY_900}">10 字节通信协议帧</text>

  <!-- 10个字节方块 -->
  <rect x="60" y="60" width="55" height="60" rx="6" fill="{GREEN_LIGHT}" stroke="{GREEN}" stroke-width="2"/>
  <text x="87" y="86" text-anchor="middle" font-family="Consolas" font-size="12" font-weight="bold" fill="{GREEN}">0xAA</text>
  <text x="87" y="106" text-anchor="middle" font-family="Microsoft YaHei" font-size="10" fill="{GRAY_700}">起始字节</text>

  <rect x="118" y="60" width="55" height="60" rx="6" fill="{BLUE_LIGHT}" stroke="{BLUE}" stroke-width="2"/>
  <text x="145" y="86" text-anchor="middle" font-family="Consolas" font-size="12" font-weight="bold" fill="{BLUE}">CMD</text>
  <text x="145" y="106" text-anchor="middle" font-family="Microsoft YaHei" font-size="10" fill="{GRAY_700}">命令</text>

  <rect x="176" y="60" width="55" height="60" rx="6" fill="{BLUE_LIGHT}" stroke="{BLUE}" stroke-width="2"/>
  <text x="203" y="86" text-anchor="middle" font-family="Consolas" font-size="12" font-weight="bold" fill="{BLUE}">ADDR</text>
  <text x="203" y="106" text-anchor="middle" font-family="Microsoft YaHei" font-size="10" fill="{GRAY_700}">地址</text>

  <rect x="234" y="60" width="55" height="60" rx="6" fill="{BLUE_LIGHT}" stroke="{BLUE}" stroke-width="2"/>
  <text x="261" y="86" text-anchor="middle" font-family="Consolas" font-size="12" font-weight="bold" fill="{BLUE}">SIGN</text>
  <text x="261" y="106" text-anchor="middle" font-family="Microsoft YaHei" font-size="10" fill="{GRAY_700}">正负号</text>

  <rect x="292" y="60" width="55" height="60" rx="6" fill="{GREEN_LIGHT}" stroke="{GREEN}" stroke-width="2"/>
  <text x="319" y="82" text-anchor="middle" font-family="Consolas" font-size="12" font-weight="bold" fill="{GREEN}">Byte5</text>
  <text x="319" y="106" text-anchor="middle" font-family="Microsoft YaHei" font-size="10" fill="{GRAY_700}">重量高</text>

  <rect x="350" y="60" width="55" height="60" rx="6" fill="{GREEN_LIGHT}" stroke="{GREEN}" stroke-width="2"/>
  <text x="377" y="82" text-anchor="middle" font-family="Consolas" font-size="12" font-weight="bold" fill="{GREEN}">Byte6</text>
  <text x="377" y="106" text-anchor="middle" font-family="Microsoft YaHei" font-size="10" fill="{GRAY_700}">重量中</text>

  <rect x="408" y="60" width="55" height="60" rx="6" fill="{GREEN_LIGHT}" stroke="{GREEN}" stroke-width="2"/>
  <text x="435" y="82" text-anchor="middle" font-family="Consolas" font-size="12" font-weight="bold" fill="{GREEN}">Byte7</text>
  <text x="435" y="106" text-anchor="middle" font-family="Microsoft YaHei" font-size="10" fill="{GRAY_700}">重量低</text>

  <rect x="466" y="60" width="55" height="60" rx="6" fill="{ORANGE_LIGHT}" stroke="{ORANGE}" stroke-width="2"/>
  <text x="493" y="82" text-anchor="middle" font-family="Consolas" font-size="12" font-weight="bold" fill="#b45309">CHK_H</text>
  <text x="493" y="106" text-anchor="middle" font-family="Microsoft YaHei" font-size="10" fill="{GRAY_700}">校验高</text>

  <rect x="524" y="60" width="55" height="60" rx="6" fill="{ORANGE_LIGHT}" stroke="{ORANGE}" stroke-width="2"/>
  <text x="551" y="82" text-anchor="middle" font-family="Consolas" font-size="12" font-weight="bold" fill="#b45309">CHK_L</text>
  <text x="551" y="106" text-anchor="middle" font-family="Microsoft YaHei" font-size="10" fill="{GRAY_700}">校验低</text>

  <rect x="582" y="60" width="55" height="60" rx="6" fill="{RED_LIGHT}" stroke="{RED}" stroke-width="2"/>
  <text x="609" y="86" text-anchor="middle" font-family="Consolas" font-size="12" font-weight="bold" fill="{RED}">0xFF</text>
  <text x="609" y="106" text-anchor="middle" font-family="Microsoft YaHei" font-size="10" fill="{GRAY_700}">结束字节</text>

  <!-- 重量 24 位括弧 -->
  <path d="M 288 55 Q 292 48 350 48 Q 408 48 412 55" fill="none" stroke="{GREEN}" stroke-width="2"/>
  <text x="350" y="44" text-anchor="middle" font-family="Microsoft YaHei" font-size="12" font-weight="bold" fill="{GREEN}">24 位重量值 (3 字节)</text>

  <!-- 校验说明 -->
  <rect x="60" y="145" width="650" height="55" rx="10" fill="{GRAY_100}" stroke="{GRAY_200}" stroke-width="1"/>
  <text x="385" y="168" text-anchor="middle" font-family="Microsoft YaHei" font-size="12" font-weight="bold" fill="{GRAY_900}">校验规则：Byte2 + Byte3 + ... + Byte7 的和 = (Byte8×256 + Byte9)</text>
  <text x="385" y="188" text-anchor="middle" font-family="Microsoft YaHei" font-size="12" fill="{GRAY_700}">例如：A3 + 00 + 00 + 00 + 00 + 32 = 0xD5 → Byte8=00, Byte9=D5 ✓</text>
"""
)


print(f"已生成 {len(os.listdir(IMAGES_DIR))} 张 SVG 图到 {IMAGES_DIR}/")
for f in sorted(os.listdir(IMAGES_DIR)):
    print(f"  - images/{f}")
