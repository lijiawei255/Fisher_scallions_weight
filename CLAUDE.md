# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Fisher_scallions_weight** — 大葱称重上位机，北京交通大学慧鱼机创赛项目。适配 1kg 量程 HX711 TTL 变送器电子秤（CMCU-07 协议 V3.70）。

核心亮点：推板下压干扰时，重量稳定后立即锁定，确保累计总重不受影响。

## Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py

# Package into single exe (Windows)
python build.py
# Output: dist/葱称重系统V2.exe
```

Dependencies: `pyserial` (serial communication), `pyinstaller` (packaging).

Python 3.8+ required. Windows primary (macOS/Linux compatible for virtual mode).

## Architecture

The project follows a clean layered architecture — 8 files, each with a single responsibility:

```
┌──────────────────────────────────────────────────────────┐
│  main.py                     — Entry point                │
│  app.py                      — UI (Tkinter)              │
│  ├── calibration.py          — Session ops (tare/untare)  │
│  │   └── scale_driver.py     — Serial driver / simulated  │
│  │       └── scale_protocol.py — 10-byte frame parsing    │
│  ├── weight_filter.py        — Stability judgment         │
│  └── weight_state.py         — Business state machine     │
│  smooth_number.py            — Number animation           │
│  config.py                   — All configurable constants  │
└──────────────────────────────────────────────────────────┘
```

### Data Pipeline

```
Hardware (100ms auto-send) → FrameParser (scale_protocol.py)
  → StableJudge (weight_filter.py) → WeightAccumulator (weight_state.py)
  → SmoothNumberAnimator (smooth_number.py) → UI (app.py)
```

### Key Modules

| File | Responsibility |
|------|---------------|
| [config.py](config.py) | All tunable constants: thresholds, baud rate, colors, timeouts |
| [scale_protocol.py](scale_protocol.py) | CMCU-07 protocol: 10-byte frame construction, parsing, checksum validation, sliding window parser for cross-packet handling |
| [scale_driver.py](scale_driver.py) | Serial driver (`ScaleDriver`) + virtual test driver (`SimulatedScaleDriver`) with identical interfaces. All serial I/O protected by `_io_lock` |
| [weight_filter.py](scale_filter.py) | Stability judgment: delays 1 sample (100ms) on value change to confirm new value, filters transient spikes |
| [weight_state.py](weight_state.py) | Business state machine: IDLE↔WEIGHING, weight locking, total accumulation. Locks weight on first stability, ignores push-plate pressure spikes |
| [calibration.py](calibration.py) | Session-level operations: tare/untare with stop-auto-send → flush → action → restart sequence |
| [app.py](app.py) | Tkinter UI: bubble particle background, Toast notifications, pill buttons, smooth number animation, auto-reconnect logic |
| [smooth_number.py](smooth_number.py) | ease-out cubic number animation with color following (green=stable, light-green=changing) |
| [build.py](build.py) | PyInstaller one-file packaging script |

### Critical Design Decisions

1. **Hardware filtering**: The CMCU-07 already has median filter(3) + average filter(3), so software reads raw values directly — no additional software filtering needed.
2. **Auto-send mode**: The scale pushes data every 100ms automatically. The UI refresh cycle is also 100ms for perfect alignment.
3. **Thread safety**: `ScaleDriver` uses `_io_lock` for all serial operations. Tare/untare run on background threads with UI polling for completion.
4. **Virtual test mode**: Set `SIMULATE_MODE_DEFAULT = True` in [config.py](config.py) to test without hardware — generates valid 10-byte protocol frames with 0g→30g→0g cycle.
5. **Auto-reconnect**: Up to 30 retries (~60s) with port auto-refresh when USB connection is lost. Transient error tolerance (3 consecutive failures before declaring disconnect).

### Protocol Constants

- Frame: 10 bytes `[0xAA][CMD][ADDR][SIGN][W_HI][W_MID][W_LO][CHK_H][CHK_L][0xFF]`
- Checksum: `sum(buf[1:7]) == (buf[7] << 8) | buf[8]`
- Default baud rate: 9600
- Default resolution: 1g/tick
- Weight threshold: 2g (enter/exit WEIGHING)
- Stability threshold: 1g (±1g fluctuation allowed)

## Project Structure

```
Fisher_scallions_weight/
├── main.py                 # Entry point
├── app.py                  # UI (Tkinter, Apple-style design)
├── config.py               # All configurable constants
├── scale_protocol.py       # 10-byte frame protocol parsing
├── scale_driver.py         # Serial driver + simulated driver
├── weight_filter.py        # Stability judgment (1-sample delay)
├── weight_state.py         # Business state machine (IDLE/WEIGHING)
├── calibration.py          # Tare/untare session operations
├── smooth_number.py        # Smooth number animation with color
├── build.py                # PyInstaller packaging script
├── generate_diagrams.py    # Generate SVG diagrams for README
├── requirements.txt        # Dependencies (pyserial, pyinstaller)
├── README.md               # Comprehensive documentation (Chinese)
├── images/                 # README SVG diagrams
│   ├── architecture.svg    # Data pipeline overview
│   ├── data_locking.svg    # Push-plate interference locking
│   ├── state_machine.svg   # IDLE/WEIGHING state machine
│   ├── stable_judge.svg    # Stability judgment logic
│   ├── total_weight.svg    # Total weight accumulation
│   ├── weighing_timeline.svg  # Complete weighing timeline
│   └── protocol_frame.svg  # 10-byte protocol frame format
├── 电子秤资料/              # Hardware vendor docs (not part of codebase)
├── build/                  # PyInstaller build output (gitignored)
└── dist/                   # Packaged exe output (gitignored)
```
