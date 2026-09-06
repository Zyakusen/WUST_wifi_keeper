# WUST_wifi_keeper

一个轻量的抗断网武汉科技大学校园网自动认证工具

## 核心特性

- **全自动无感运行**：开机后自动隐藏至系统托盘，静默维持网络连接。
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

## 源码编译（开发者用户）

项目使用 [uv](https://docs.astral.sh/uv/) 管理依赖，GUI 基于 customtkinter，打包使用 Nuitka。

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

## 免责声明

本项目仅供编程学习与交流使用，账号密码仅保存在本地，请遵守学校网络使用规范。
