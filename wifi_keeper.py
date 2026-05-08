import os
import sys
import time
import requests
import subprocess
import re
import json
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext
from datetime import datetime
import pystray
from PIL import Image, ImageDraw

# 终端日志颜色配置
class Color:
    SYSTEM = '\033[96m'
    SUCCESS = '\033[92m'
    INFO = '\033[94m'
    WARN = '\033[93m'
    ERROR = '\033[91m'
    PROBE = '\033[37m'
    RESET = '\033[0m'

os.system('') 

# 路径配置：兼容 PyInstaller 单文件打包环境
if getattr(sys, 'frozen', False):
    SCRIPT_DIR = os.path.dirname(sys.executable)
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(SCRIPT_DIR, "wifi_config.json")
LOG_FILE = os.path.join(SCRIPT_DIR, "wifi_keeper.log")

# 全局状态变量
is_running = False
WIFI_NAME = ""
LOGIN_URL = "http://59.68.177.9/api/account/login"
PAYLOAD = {"username": "", "password": "", "nasId": "2"}
HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
RECONNECT_DELAY_SECONDS = 5

# 初始化日志文件
open(LOG_FILE, 'w', encoding='utf-8').close()

def log(level, message):
    """将日志写入文件并附带时间戳"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] [{level}] {message}\n")
    except Exception:
        pass

def check_connectivity():
    """验证广域网连通性"""
    try:
        start_time = time.time()
        response = requests.get("http://www.msftconnecttest.com/connecttest.txt", timeout=3, allow_redirects=False)
        latency = int((time.time() - start_time) * 1000)
        
        if response.status_code == 200 and "Microsoft Connect Test" in response.text:
            log("PROBE", f"广域网畅通 (延迟: {latency}ms)")
            return True
        return False
    except Exception:
        return False

def reconnect_wifi():
    """强制重连系统 Wi-Fi"""
    log("WARN", f"正在重连系统 Wi-Fi: {WIFI_NAME}")
    creationflags = 0
    startupinfo = None
    if os.name == "nt":
        try:
            creationflags = subprocess.CREATE_NO_WINDOW
        except AttributeError:
            pass
        try:
            startupinfo = subprocess.STARTUPINFO()
        except AttributeError:
            startupinfo = None
        if startupinfo is not None:
            try:
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
            except AttributeError:
                pass
    try:
        subprocess.run(
            ["netsh", "wlan", "connect", f"name={WIFI_NAME}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
            startupinfo=startupinfo,
            check=False,
        )
    except Exception as e:
        log("ERROR", f"重连命令执行异常: {e}")
    time.sleep(RECONNECT_DELAY_SECONDS) 

def perform_login():
    """发送认证请求"""
    log("INFO", "正在提交认证请求...")
    try:
        response = requests.post(LOGIN_URL, data=PAYLOAD, headers=HEADERS, timeout=5)
        if response.status_code == 200:
            log("SUCCESS", "认证成功")
            return True
        else:
            log("ERROR", f"认证被拒。状态码: {response.status_code}")
            return False
    except Exception as e:
        log("ERROR", f"认证服务器连接异常: {e}")
        return False

def monitor_loop():
    """核心守护线程"""
    global is_running
    log("SYSTEM", f"后台守护已启动，目标网络: {WIFI_NAME} (nasId: {PAYLOAD['nasId']})")
    
    while is_running:
        if check_connectivity():
            # 正常情况下保持静默并定期轮询
            for _ in range(10):
                if not is_running: break
                time.sleep(2)
        else:
            log("WARN", "检测到网络断开，执行重连逻辑")
            if not perform_login():
                reconnect_wifi()
                perform_login()
            log("SYSTEM", "重连流程完毕")
            for _ in range(5):
                if not is_running: break
                time.sleep(1)

def load_config():
    """读取本地 JSON 配置"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # 向下兼容：如果旧配置文件没有 nasId，自动补全默认值 2
                if "nasId" not in data:
                    data["nasId"] = "2"
                return data
        except Exception:
            pass
    return {"wifi_name": "WUST-WiFi6", "username": "", "password": "", "nasId": "2"}

def save_config(wifi, user, pwd, nas_id):
    """保存配置至本地"""
    config = {"wifi_name": wifi, "username": user, "password": pwd, "nasId": nas_id}
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        log("ERROR", f"配置写入失败: {e}")

def create_tray_image():
    """生成系统托盘图标"""
    image = Image.new('RGB', (64, 64), color=(0, 120, 215))
    dc = ImageDraw.Draw(image)
    dc.rectangle([16, 16, 48, 48], fill="white")
    return image

def setup_gui():
    global is_running, WIFI_NAME, PAYLOAD
    config = load_config()

    root = tk.Tk()
    root.title("校园网守护")
    
    # 窗口居中
    window_width, window_height = 320, 320
    x = int((root.winfo_screenwidth() - window_width) / 2)
    y = int((root.winfo_screenheight() - window_height) / 2)
    root.geometry(f'{window_width}x{window_height}+{x}+{y}')
    root.resizable(False, False)

    # 拦截关闭按钮行为：转为隐藏
    root.protocol("WM_DELETE_WINDOW", lambda: root.withdraw())

    padding_opt = {'padx': 20, 'pady': 3}

    tk.Label(root, text="Wi-Fi 名称:").pack(anchor="w", **padding_opt)
    entry_wifi = tk.Entry(root, width=35)
    entry_wifi.pack(**padding_opt)
    entry_wifi.insert(0, config.get('wifi_name', ''))

    tk.Label(root, text="学号 (Username):").pack(anchor="w", **padding_opt)
    entry_user = tk.Entry(root, width=35)
    entry_user.pack(**padding_opt)
    entry_user.insert(0, config.get('username', ''))

    tk.Label(root, text="密码 (Password):").pack(anchor="w", **padding_opt)
    entry_pwd = tk.Entry(root, width=35, show="*")
    entry_pwd.pack(**padding_opt)
    entry_pwd.insert(0, config.get('password', ''))

    tk.Label(root, text="网关 ID (nasId - 默认填 2):").pack(anchor="w", **padding_opt)
    entry_nasid = tk.Entry(root, width=35)
    entry_nasid.pack(**padding_opt)
    entry_nasid.insert(0, config.get('nasId', '2'))

    def start_monitoring():
        """启动后台服务"""
        global is_running
        root.withdraw()
        if not is_running:
            is_running = True
            threading.Thread(target=monitor_loop, daemon=True).start()

    def on_submit():
        """保存配置并启动"""
        global WIFI_NAME
        wifi = entry_wifi.get().strip()
        user = entry_user.get().strip()
        pwd = entry_pwd.get().strip()
        nas_id = entry_nasid.get().strip()

        if not wifi or not user or not pwd or not nas_id:
            messagebox.showwarning("输入错误", "参数不能为空")
            return

        save_config(wifi, user, pwd, nas_id)
        WIFI_NAME = wifi
        PAYLOAD["username"] = user
        PAYLOAD["password"] = pwd
        PAYLOAD["nasId"] = nas_id
        
        start_monitoring()

    def show_log_window():
        """显示日志查阅窗口"""
        log_win = tk.Toplevel(root)
        log_win.title("运行日志")
        log_win.geometry("600x400")
        
        txt = scrolledtext.ScrolledText(log_win, font=("Consolas", 9), bg="#1e1e1e", fg="#cccccc")
        txt.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        txt.tag_config("SYSTEM", foreground="#56b6c2")
        txt.tag_config("SUCCESS", foreground="#98c379")
        txt.tag_config("INFO", foreground="#61afef")
        txt.tag_config("WARN", foreground="#e5c07b")
        txt.tag_config("ERROR", foreground="#e06c75")
        txt.tag_config("PROBE", foreground="#7f848e")

        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    match = re.search(r'\[(SYSTEM|SUCCESS|INFO|WARN|ERROR|PROBE)\]', line)
                    if match:
                        txt.insert(tk.END, line, match.group(1))
                    else:
                        txt.insert(tk.END, line)
        except Exception:
            txt.insert(tk.END, "暂无日志产生。")

        txt.see(tk.END)
        txt.config(state=tk.DISABLED)

    # 底部按钮区
    btn_frame = tk.Frame(root)
    btn_frame.pack(pady=15)
    tk.Button(btn_frame, text="保存并隐藏监控", bg="#0078D7", fg="white", width=18, command=on_submit).pack(pady=2)
    tk.Button(btn_frame, text="查看运行日志", width=18, command=show_log_window).pack(pady=2)

    # 托盘相关逻辑
    def on_show_window(icon, item):
        root.after(0, root.deiconify)

    def on_show_log(icon, item):
        root.after(0, show_log_window)

    def on_quit(icon, item):
        global is_running
        is_running = False
        icon.stop()
        root.after(0, root.destroy)

    def run_tray():
        menu = pystray.Menu(
            pystray.MenuItem("控制面板", on_show_window, default=True),
            pystray.MenuItem("查看日志", on_show_log),
            pystray.MenuItem("退出监控", on_quit)
        )
        icon = pystray.Icon("WiFiKeeper", create_tray_image(), "校园网守护", menu)
        icon.run()

    threading.Thread(target=run_tray, daemon=True).start()

    # 静默启动校验
    if config.get('wifi_name') and config.get('username') and config.get('password'):
        WIFI_NAME = config['wifi_name']
        PAYLOAD['username'] = config['username']
        PAYLOAD['password'] = config['password']
        # 兼容静默启动时的 nasId 读取
        PAYLOAD['nasId'] = config.get('nasId', '2')
        
        # 隐藏主窗口并直接开启监控任务
        root.withdraw()
        root.after(0, start_monitoring)
    
    root.mainloop()

if __name__ == "__main__":
    setup_gui()
