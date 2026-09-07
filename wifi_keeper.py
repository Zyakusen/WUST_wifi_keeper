import os
import sys
import time
import shutil
import requests
import subprocess
import re
import json
import threading
import customtkinter as ctk
from tkinter import messagebox
from datetime import datetime
try:
    import pystray
except Exception:
    pystray = None
from PIL import Image, ImageDraw
try:
    from PIL import ImageTk
except ImportError:
    ImageTk = None

# 路径配置：兼容 PyInstaller / Nuitka 单文件打包环境
def resolve_script_dir():
    """确定程序所在目录（配置/日志/图标都存放于此）

    优先取 Nuitka 的 __compiled__.containing_dir（原始可执行文件所在目录，
    onefile/standalone 通用）；否则回退：单文件模式下 sys.frozen 为 None、
    __file__ 在临时解压目录，只有 sys.argv[0] 指向原始可执行文件路径。
    """
    if "__compiled__" in globals():
        # Nuitka：__compiled__.containing_dir 恒为原始可执行文件所在目录
        # （onefile/standalone 通用，且不受用户改名影响）
        try:
            dir_ = __compiled__.containing_dir  # noqa: F821
            if dir_ and os.path.isdir(dir_):
                return dir_
        except Exception:
            pass
    exe = os.path.abspath(sys.argv[0])
    if exe.lower().endswith((".exe", ".bin")):
        # Nuitka / PyInstaller 单文件：argv[0] 即原始可执行文件路径
        # （Windows .exe / Linux .bin）
        return os.path.dirname(exe)
    if getattr(sys, 'frozen', False):
        # PyInstaller（异常情况下 argv[0] 不可靠时的兜底）
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

SCRIPT_DIR = resolve_script_dir()

CONFIG_FILE = os.path.join(SCRIPT_DIR, "wifi_config.json")
LOG_FILE = os.path.join(SCRIPT_DIR, "wifi_keeper.log")

# 全局状态变量
is_running = False
WIFI_NAME = ""
LOGIN_URL = "http://59.68.177.9/api/account/login"
PAYLOAD = {"username": "", "password": "", "nasId": "2"}
_UA_OS = "Windows NT 10.0; Win64; x64" if sys.platform == "win32" else "X11; Linux x86_64"
HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "User-Agent": f"Mozilla/5.0 ({_UA_OS}) AppleWebKit/537.36"
}

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

MONO_FONT = ("Consolas", 12) if sys.platform == "win32" else ("DejaVu Sans Mono", 12)
LOG_FONT = MONO_FONT  # 日志窗口字体（Linux 下由 setup_linux_fonts 覆盖为含中文的字体）
CJK_FONT_CANDIDATES = (
    "Noto Sans CJK SC", "Noto Sans SC", "Source Han Sans SC", "WenQuanYi Micro Hei",
    "WenQuanYi Zen Hei", "Droid Sans Fallback", "AR PL UMing CN",
    "Noto Sans CJK JP", "Noto Sans CJK KR",
)
# Linux 的 pystray xorg 后端不支持右键菜单；HAS_MENU 为 False 时
# 窗口保持可见并提供窗口内退出按钮（Windows 行为不变）
TRAY_HAS_MENU = pystray is not None and getattr(pystray.Icon, "HAS_MENU", True)

def _run_silently(cmd):
    """无窗口执行系统命令（Windows 下避免闪现控制台窗口）"""
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)

def _find_wireless_interface():
    """Linux 下发现无线网卡接口名（iwctl 需要显式接口名）

    首选内核 sysfs：/sys/class/net/<iface>/wireless 目录仅存在于无线设备上，
    无需解析外部命令输出；失败时退化为解析 iwctl station list 首列。
    """
    try:
        for name in sorted(os.listdir("/sys/class/net")):
            if os.path.isdir(os.path.join("/sys/class/net", name, "wireless")):
                return name
    except Exception:
        pass
    try:
        out = subprocess.run(["iwctl", "station", "list"],
                             capture_output=True, text=True, timeout=5)
        for line in out.stdout.splitlines():
            parts = line.split()
            if parts and parts[0].lower().startswith(("wl", "wlp")):
                return parts[0]
    except Exception:
        pass
    return None

def reconnect_linux():
    """Linux：优先 nmcli（NetworkManager），缺失或失败时回退 iwctl（iwd）"""
    if shutil.which("nmcli"):
        result = subprocess.run(["nmcli", "device", "wifi", "connect", WIFI_NAME],
                                capture_output=True, text=True)
        if result.returncode == 0:
            return
        log("ERROR", f"nmcli 重连失败: {result.stderr.strip()}")
    if shutil.which("iwctl"):
        iface = _find_wireless_interface()
        if iface:
            subprocess.run(["iwctl", "station", iface, "connect", WIFI_NAME],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            log("ERROR", "未找到无线网卡接口，iwctl 重连失败")
    else:
        log("ERROR", "未找到可用的重连后端 (nmcli/iwctl)，无法自动重连 Wi-Fi")

def reconnect_wifi():
    """强制重连系统 Wi-Fi（无控制台窗口弹出）"""
    log("WARN", f"正在重连系统 Wi-Fi: {WIFI_NAME}")
    if sys.platform == "win32":
        _run_silently(["netsh", "wlan", "connect", f"name={WIFI_NAME}"])
    else:
        reconnect_linux()
    time.sleep(5)

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

def get_icon_file():
    """定位 icon.ico：优先程序同目录，其次 Nuitka onefile 内置副本"""
    candidates = [os.path.join(SCRIPT_DIR, "icon.ico")]
    try:
        candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico"))
    except Exception:
        pass
    for path in candidates:
        if os.path.exists(path):
            return path
    return None

def get_window_icon_path():
    """窗口图标来源：打包后取 exe 内嵌图标，开发环境用目录内 icon.ico"""
    if getattr(sys, 'frozen', False):
        return sys.executable
    return get_icon_file()

def get_bundled_font_file():
    """定位内置中文字体：优先程序同目录，其次 Nuitka onefile 内置副本"""
    candidates = [os.path.join(SCRIPT_DIR, "assets", "fonts", "NotoSansSC-Subset.woff2")]
    try:
        candidates.append(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "assets", "fonts", "NotoSansSC-Subset.woff2"))
    except Exception:
        pass
    for path in candidates:
        if os.path.exists(path):
            return path
    return None

def setup_linux_fonts(root):
    """Linux：注册内置中文字体并从已安装字体中挑选含中文的字体族

    Tk/X11 不保证对缺失字形做字体回退，而默认字体（Roboto/DejaVu）没有
    中文字形，因此必须显式选择含中文的字体族。
    """
    global LOG_FONT
    try:
        import tkinter.font as tkfont
        font_file = get_bundled_font_file()
        if font_file:
            # customtkinter 的 FontManager 会将其复制到 ~/.fonts 供 fontconfig 识别
            ctk.FontManager.load_font(font_file)
            if shutil.which("fc-cache"):
                subprocess.run(["fc-cache", "-f", os.path.expanduser("~/.fonts")],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        families = set(tkfont.families(root))
        for fam in CJK_FONT_CANDIDATES:
            if fam in families:
                ctk.ThemeManager.theme["CTkFont"]["family"] = fam
                tkfont.nametofont("TkDefaultFont").configure(family=fam)
                LOG_FONT = (fam, 12)
                log("SYSTEM", f"中文字体: {fam}")
                return
    except Exception as e:
        log("ERROR", f"中文字体设置失败: {e}")
    log("WARN", "未找到中文字体，界面中文可能无法正常显示（可安装 fonts-noto-cjk）")

def create_tray_image():
    """生成系统托盘图标：优先使用 icon.ico，失败时程序绘制"""
    icon_file = get_icon_file()
    if icon_file:
        try:
            img = Image.open(icon_file).convert("RGBA")
            img.thumbnail((64, 64), Image.LANCZOS)
            return img
        except Exception:
            pass
    # 兜底：程序绘制
    image = Image.new('RGB', (64, 64), color=(0, 120, 215))
    dc = ImageDraw.Draw(image)
    dc.rectangle([16, 16, 48, 48], fill="white")
    return image

def setup_gui():
    global is_running, WIFI_NAME, PAYLOAD
    config = load_config()

    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.title("校园网守护")

    if sys.platform != "win32":
        # 必须在创建任何控件之前完成字体族切换
        setup_linux_fonts(root)

    # 窗口图标：打包后取 exe 内嵌图标，开发环境用目录内 icon.ico
    # 注意：Windows 下 iconbitmap 的 default= 形式无效，必须逐窗口设置
    def apply_window_icon(window):
        try:
            if sys.platform == "win32":
                icon_path = get_window_icon_path()
                if icon_path:
                    window.iconbitmap(icon_path)
            elif ImageTk is not None:
                # Linux：iconbitmap 不支持 ico，改用 iconphoto + PIL 图像
                photo = ImageTk.PhotoImage(create_tray_image())
                window.iconphoto(True, photo)
                window._iconphoto_ref = photo  # 必须保持引用，否则被垃圾回收
        except Exception:
            pass

    apply_window_icon(root)

    # 窗口居中
    window_width, window_height = 380, 480
    x = int((root.winfo_screenwidth() - window_width) / 2)
    y = int((root.winfo_screenheight() - window_height) / 2)
    root.geometry(f'{window_width}x{window_height}+{x}+{y}')
    root.resizable(False, False)

    tray_icon = {}  # 持有托盘图标引用，供窗口内"退出"按钮调用

    def quit_app():
        global is_running
        is_running = False
        icon = tray_icon.get("icon")
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass
        root.after(0, root.destroy)

    # 拦截关闭按钮行为：托盘有菜单时转为隐藏；否则直接退出
    def on_close():
        if TRAY_HAS_MENU:
            root.withdraw()
        else:
            quit_app()

    root.protocol("WM_DELETE_WINDOW", on_close)

    padding_opt = {'padx': 20, 'pady': 5}

    ctk.CTkLabel(root, text="Wi-Fi 名称:").pack(anchor="w", **padding_opt)
    entry_wifi = ctk.CTkEntry(root, width=320, placeholder_text="如 WUST-WiFi6")
    entry_wifi.pack(**padding_opt)
    entry_wifi.insert(0, config.get('wifi_name', ''))

    ctk.CTkLabel(root, text="学号 (Username):").pack(anchor="w", **padding_opt)
    entry_user = ctk.CTkEntry(root, width=320)
    entry_user.pack(**padding_opt)
    entry_user.insert(0, config.get('username', ''))

    ctk.CTkLabel(root, text="密码 (Password):").pack(anchor="w", **padding_opt)
    entry_pwd = ctk.CTkEntry(root, width=320, show="*")
    entry_pwd.pack(**padding_opt)
    entry_pwd.insert(0, config.get('password', ''))

    ctk.CTkLabel(root, text="网关 ID (nasId - 默认填 2):").pack(anchor="w", **padding_opt)
    entry_nasid = ctk.CTkEntry(root, width=320)
    entry_nasid.pack(**padding_opt)
    entry_nasid.insert(0, config.get('nasId', '2'))

    def start_monitoring():
        """启动后台服务"""
        global is_running
        if TRAY_HAS_MENU:
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
        """显示日志查阅窗口（实时刷新）"""
        log_win = ctk.CTkToplevel(root)
        log_win.title("运行日志")
        log_win.geometry("640x420")
        apply_window_icon(log_win)

        txt = ctk.CTkTextbox(log_win, font=LOG_FONT, fg_color="#1e1e1e", text_color="#cccccc")
        txt.pack(fill="both", expand=True, padx=10, pady=10)

        txt.tag_config("SYSTEM", foreground="#56b6c2")
        txt.tag_config("SUCCESS", foreground="#98c379")
        txt.tag_config("INFO", foreground="#61afef")
        txt.tag_config("WARN", foreground="#e5c07b")
        txt.tag_config("ERROR", foreground="#e06c75")
        txt.tag_config("PROBE", foreground="#7f848e")

        def insert_line(line):
            """插入一行日志并按级别着色"""
            match = re.search(r'\[(SYSTEM|SUCCESS|INFO|WARN|ERROR|PROBE)\]', line)
            txt.insert("end", line, match.group(1) if match else None)

        def load_full():
            """整体重载日志文件"""
            txt.configure(state="normal")
            txt.delete("1.0", "end")
            try:
                with open(LOG_FILE, "r", encoding="utf-8") as f:
                    for line in f:
                        insert_line(line)
            except Exception:
                txt.insert("end", "暂无日志产生。")
            txt.configure(state="disabled")

        offset = [0]  # 日志文件已读取到的偏移量

        def refresh():
            """每秒检查一次日志文件，把新增行追加到窗口"""
            if not log_win.winfo_exists():
                return
            try:
                size = os.path.getsize(LOG_FILE)
                if size < offset[0]:
                    # 文件被截断（程序重启等），整体重载
                    offset[0] = 0
                    load_full()
                    txt.see("end")
                elif size > offset[0]:
                    was_at_bottom = txt.yview()[1] >= 0.95
                    txt.configure(state="normal")
                    with open(LOG_FILE, "r", encoding="utf-8") as f:
                        f.seek(offset[0])
                        for line in f:
                            insert_line(line)
                        offset[0] = f.tell()
                    txt.configure(state="disabled")
                    if was_at_bottom:
                        txt.see("end")
            except Exception:
                pass
            log_win.after(1000, refresh)

        load_full()
        txt.see("end")
        log_win.after(1000, refresh)

    # 底部按钮区
    btn_frame = ctk.CTkFrame(root, fg_color="transparent")
    btn_frame.pack(pady=15)
    ctk.CTkButton(btn_frame, text="保存并隐藏监控", fg_color="#0078D7", hover_color="#005A9E",
                  text_color="white", width=320, command=on_submit).pack(pady=4)
    ctk.CTkButton(btn_frame, text="查看运行日志", fg_color="transparent", border_width=1,
                  width=320, command=show_log_window).pack(pady=4)
    if not TRAY_HAS_MENU:
        # Linux 托盘（xorg 后端）无右键菜单，提供窗口内退出入口
        ctk.CTkButton(btn_frame, text="退出", fg_color="#d33d3d", hover_color="#b22f2f",
                      text_color="white", width=320, command=quit_app).pack(pady=4)

    # 托盘相关逻辑
    def on_show_window(icon, item):
        root.after(0, root.deiconify)

    def on_show_log(icon, item):
        root.after(0, show_log_window)

    def on_quit(icon, item):
        quit_app()

    def run_tray():
        if pystray is None:
            log("ERROR", "托盘图标不可用，无法常驻托盘")
            return
        menu = pystray.Menu(
            pystray.MenuItem("控制面板", on_show_window, default=True),
            pystray.MenuItem("查看日志", on_show_log),
            pystray.MenuItem("退出监控", on_quit)
        )
        icon = pystray.Icon("WiFiKeeper", create_tray_image(), "校园网守护", menu)
        tray_icon["icon"] = icon
        try:
            icon.run()
        except Exception:
            log("ERROR", "托盘图标启动失败，窗口保持可见")
            root.after(0, root.deiconify)

    threading.Thread(target=run_tray, daemon=True).start()

    # 静默启动校验
    if config.get('wifi_name') and config.get('username') and config.get('password'):
        WIFI_NAME = config['wifi_name']
        PAYLOAD['username'] = config['username']
        PAYLOAD['password'] = config['password']
        # 兼容静默启动时的 nasId 读取
        PAYLOAD['nasId'] = config.get('nasId', '2')

        # 隐藏主窗口并直接开启监控任务
        if TRAY_HAS_MENU:
            root.withdraw()
        root.after(0, start_monitoring)

    root.mainloop()

if __name__ == "__main__":
    setup_gui()
