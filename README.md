# WUST_wifi_keeper

一个轻量的抗断网武汉科技大学校园网自动认证工具

## 核心特性

- **全自动无感运行**：开机后自动隐藏至系统托盘，静默维持网络连接（支持 Windows 与 Linux）。
- **双层探针检测**：通过 HTTP 探针精准识别网关劫持，防 ICMP（Ping）穿透误判。
- **物理断线自愈**：当 Wi-Fi 彻底断开时，可直接调动底层网卡自动重连。
- **多校区支持**：开放 `nasId` 参数配置，兼容黄家湖/青山等不同校区网关。
- **日志记录**：内置实时刷新的日志查看器，随时追踪网络状态。
- **无黑窗运行**：重连 Wi-Fi 等系统调用使用无窗口方式执行，不闪现控制台窗口。

## 快速开始（普通用户）

1. 前往右侧的 [Releases](https://github.com/Zyakusen/WUST_wifi_keeper/releases/latest) 页面下载最新版本的 `wifi_keeper.exe`。
2. 双击运行，在弹出的窗口中填入：
   - **Wi-Fi 名称** (如: `WUST-WiFi6`)
   - **学号** 和 **密码**
   - **网关 ID (nasId)**：黄家湖默认填 `2`，青山校区可通过浏览器开发者工具抓包获取。
3. 点击"保存并隐藏监控"，程序将自动最小化到右下角托盘。
4. **注意**：程序会在同级目录下生成 `wifi_config.json` 存储配置，请勿将其分享给他人。

### Linux 用户

1. 前往 [Releases](https://github.com/Zyakusen/WUST_wifi_keeper/releases/latest) 下载 `wifi_keeper.bin`，然后在**可写目录**下运行（配置与日志生成在二进制同目录）：

   ```bash
   chmod +x wifi_keeper.bin
   ./wifi_keeper.bin
   ```

2. 使用前提：
   - 桌面 Linux + X11 环境。GNOME Wayland 需安装 AppIndicator 扩展（如 "AppIndicator and KStatusNotifierItem Support"），否则托盘图标不可见，程序会保持窗口常驻。
   - 自动重连需要 NetworkManager（`nmcli`）或 iwd（`iwctl`）之一，前者覆盖绝大多数发行版；`iwctl` 通常需要 root 或 iwd 授权组权限。
   - 界面中文由内置字体（Noto Sans SC 子集，SIL OFL 1.1）渲染，无需安装系统字体。
   - WSL/WSLg 下窗口**标题栏**由 WSLg 使用系统字体绘制，若乱码请执行 `sudo apt install fonts-noto-cjk`（窗口内部文字不受影响，仅标题栏需要系统字体）。
3. Linux 托盘限制说明：二进制内置的托盘后端（X11/xorg）**不支持右键菜单**，左键单击图标可唤出窗口；请使用窗口内的"退出"按钮退出程序。源码运行时若安装了 `python3-gi` + AppIndicator，托盘菜单可用。WSL/WSLg 环境没有系统托盘，图标不会显示，程序会保持窗口常驻（属预期行为）。
4. 也可以源码方式运行（Debian/Ubuntu 需先装 tkinter）：

   ```bash
   sudo apt install python3-tk
   uv sync --python-preference only-system
   uv run python wifi_keeper.py
   ```

## 源码编译（开发者用户）

项目使用 [uv](https://docs.astral.sh/uv/) 管理依赖，GUI 基于 customtkinter，打包使用 Nuitka。
Release 中的二进制由 GitHub Actions 在每次推送 `v*` tag 时自动构建（Windows + Linux 双平台），无需手动发布。

### Windows

```bash
# 1. 安装依赖（自动创建 .venv）
uv sync

# 2. 直接运行
uv run python wifi_keeper.py

# 3. 单文件打包（无终端黑框，图标嵌入 icon.ico）
uv run python -m nuitka --onefile --windows-console-mode=disable \
    --windows-icon-from-ico=icon.ico \
    --include-package-data=customtkinter \
    --enable-plugin=tk-inter \
    --include-data-files=icon.ico=icon.ico \
    wifi_keeper.py
```

编译后的可执行文件为当前目录下的 `wifi_keeper.exe`。

### Linux

```bash
# 1. 系统依赖（tkinter 运行库 + Nuitka 所需 patchelf）
sudo apt install python3-tk patchelf

# 2. 安装依赖（必须用系统 Python：uv 自带 Python 在 Linux 上不含 tkinter）
uv sync --python-preference only-system

# 3. 直接运行
uv run python wifi_keeper.py

# 4. 单文件打包（去掉 Windows 专属参数，内置中文字体）
uv run python -m nuitka --onefile \
    --include-package-data=customtkinter \
    --enable-plugin=tk-inter \
    --include-data-files=icon.ico=icon.ico \
    --include-data-files=assets/fonts/NotoSansSC-Subset.woff2=assets/fonts/NotoSansSC-Subset.woff2 \
    --include-data-files=assets/fonts/OFL.txt=assets/fonts/OFL.txt \
    wifi_keeper.py
```

编译产物为当前目录下的 `wifi_keeper.bin`。注意：
- 构建的二进制要求 glibc ≥ 2.35（Ubuntu 22.04+ / Debian 12+ / Fedora 37+），CI 使用 ubuntu-22.04 固定此下限。
- 建议在干净环境（未安装 `python3-gi`）构建，避免二进制硬依赖 PyGObject。
- 内置字体为 Noto Sans SC 的 GB2312 子集（SIL OFL 1.1，许可证见 `assets/fonts/OFL.txt`），源码运行时也会自动加载，无需安装系统字体。

## 免责声明

本项目仅供编程学习与交流使用，账号密码仅保存在本地，请遵守学校网络使用规范。
