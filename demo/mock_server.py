"""EasyHA 演示服务器。

在本机模拟"设备端"行为（热点、WiFi、Supervisor、HA onboarding），驱动**真实的前端代码**
（addons/easy-setup/rootfs/www 向导 + app 易家面板）完整走一遍配网与初始化流程，
用于评审交互效果。设备侧真实实现见 portal/ 与 build/，本文件不含产品逻辑。

用法:  python demo/mock_server.py   →  http://127.0.0.1:8768
重置:  http://127.0.0.1:8768/api/demo/reset
面板:  http://127.0.0.1:8768/panel
"""
import io
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import qrcode
import qrcode.image.svg

ROOT = Path(__file__).resolve().parent.parent
WWW = ROOT / "addons" / "easy-setup" / "rootfs" / "www"
APP = ROOT / "addons" / "easy-setup" / "rootfs" / "app"
PORT = int(os.environ.get("PORT", "8768"))

LOCK = threading.Lock()

WIFI_LIST = [
    {"ssid": "小米路由器-5G", "strength": 92, "security": "加密"},
    {"ssid": "ChinaNet-aB3c", "strength": 78, "security": "加密"},
    {"ssid": "TP-LINK_5678", "strength": 64, "security": "加密"},
    {"ssid": "CMCC-Web", "strength": 51, "security": "加密"},
    {"ssid": "邻居的WiFi", "strength": 37, "security": "加密"},
]

STEPS_SCRIPT = {
    "components": [
        "开始下载安装 小米 Miot（小米生态设备接入）...",
        "下载失败 [直连] github.com: 连接超时",
        "镜像回退 ghfast.top 成功（2.1 MB）",
        "xiaomi_miot 安装完成（42 个文件）",
        "开始下载安装 HACS（社区插件商店）...",
        "HACS 安装完成（38 个文件）",
    ],
    "panel": [
        "configuration.yaml 已更新（时区/免登录/易家面板/发现能力）",
        "「易家」面板已写入 /config/www/easyha",
    ],
    "addons": [
        "插件 core_configurator（文件编辑器）安装成功",
        "插件 core_samba（Samba 共享）安装成功",
        "插件 core_ssh（终端）安装成功",
    ],
    "restart": [
        "Home Assistant 正在重启...",
        "Home Assistant 已重启并就绪",
    ],
    "discovery": [
        "官方引导流程已静默完成",
        "zeroconf 发现: 小米网关 / Yeelight 灯 / DLNA 渲染器",
        "自动识别到 23 个设备/实体",
    ],
}

state = {}


def reset_state():
    with LOCK:
        state.clear()
        state.update({
            "phase": "ap",            # ap → wifi
            "setup_done": False,
            "ap": {"ssid": "EasyHA-Setup", "psk": "", "ip": "192.168.4.1"},
            "wifi": None,
            "connecting": False,
            "ha_user": None,
            "entities": None,
            "steps": {},
            "log": ["[演示] 设备已启动，无网络环境，热点 EasyHA-Setup 已开启"],
        })


def log(msg):
    with LOCK:
        state["log"].append(msg)
        print("[demo]", msg, flush=True)


def _connect_worker(ssid):
    with LOCK:
        state["connecting"] = True
    log(f"正在连接 WiFi: {ssid}")
    time.sleep(6)
    with LOCK:
        state["phase"] = "wifi"
        state["wifi"] = {"ssid": ssid, "ip": "192.168.31.42"}
        state["connecting"] = False
        state["ap"] = None
    log(f"WiFi 连接成功: {ssid} (IP 192.168.31.42)，热点已关闭")


def _apply_worker(body):
    def run_step(step_id, seconds):
        with LOCK:
            state["steps"][step_id] = {"status": "running"}
        for line in STEPS_SCRIPT[step_id]:
            log(line)
            time.sleep(seconds / len(STEPS_SCRIPT[step_id]))
        with LOCK:
            state["steps"][step_id] = {"status": "done"}

    log("自动装机已启动（安装组件 → 面板 → 插件 → 重启 → 识别）")
    run_step("components", 10)
    run_step("panel", 4)
    run_step("addons", 6)
    run_step("restart", 6)
    run_step("discovery", 5)
    with LOCK:
        state["entities"] = 23
        state["setup_done"] = True
    log("🎉 初始化完成！打开 http://easyha.local:8123 即可使用")


def _qr_svg(text):
    qr = qrcode.QRCode(border=2, box_size=8, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    server_version = "EasyHADemo/1.0"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload):
        self._send(200, json.dumps(payload, ensure_ascii=False))

    def _static(self, path, ctype):
        p = Path(path)
        if not p.is_file():
            self._send(404, "not found", "text/plain")
            return
        self._send(200, p.read_bytes(), ctype)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            self._static(WWW / "index.html", "text/html; charset=utf-8")
        elif path == "/wizard.js":
            self._static(WWW / "wizard.js", "application/javascript; charset=utf-8")
        elif path == "/style.css":
            self._static(WWW / "style.css", "text/css; charset=utf-8")
        elif path == "/panel":
            self._static(Path(__file__).parent / "panel.html", "text/html; charset=utf-8")
        elif path == "/app.js":
            self._static(APP / "easyha-panel.js", "application/javascript; charset=utf-8")
        elif path == "/api/demo/reset":
            reset_state()
            self._json({"ok": True})
        elif path == "/api/status":
            with LOCK:
                mode = "wifi" if state["phase"] == "wifi" else "ap"
                self._json({
                    "ok": True, "version": "1.0.0-demo", "mode": mode,
                    "mdns": "easyha.local", "ha_url": "http://easyha.local:8123",
                    "portal_url": "http://easyha.local", "home_name": "易家",
                    "ap": dict(state["ap"]) if state["ap"] else None,
                    "wifi": dict(state["wifi"]) if state["wifi"] else None,
                    "wifi_error": None, "connecting": state["connecting"],
                    "setup_done": state["setup_done"], "ha_user": state["ha_user"],
                    "entities": state["entities"],
                    "network": {"wifi_present": True, "wifi_connected": mode == "wifi",
                                "eth_connected": False, "wifi_ssid": (state["wifi"] or {}).get("ssid"),
                                "wifi_ip": (state["wifi"] or {}).get("ip")},
                })
        elif path == "/api/wifi/list":
            self._json({"ok": True, "list": WIFI_LIST})
        elif path == "/api/wizard/progress":
            with LOCK:
                steps = json.loads(json.dumps(state["steps"]))
                done = bool(state["setup_done"])
                self._json({"ok": True, "steps": steps, "done": done,
                            "setup_done": state["setup_done"], "entities": state["entities"],
                            "log": state["log"][-50:]})
        elif path == "/api/qr":
            text = (parse_qs(parsed.query).get("text") or ["http://easyha.local"])[0]
            self._send(200, _qr_svg(text), "image/svg+xml")
        else:
            self._redirect("/")

    def _redirect(self, loc):
        self._send(302, b"", "text/plain", extra={"Location": loc})

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except Exception:
            body = {}

        if path == "/api/wifi/connect":
            ssid = (body.get("ssid") or "").strip()
            if not ssid:
                self._json({"ok": False, "error": "缺少 SSID"})
                return
            threading.Thread(target=_connect_worker, args=(ssid,), daemon=True).start()
            self._json({"ok": True})
        elif path == "/api/wizard/account":
            username = (body.get("username") or "").strip()
            password = body.get("password") or ""
            if not username or len(password) < 4:
                self._json({"ok": False, "error": "用户名或密码不符合要求（密码至少 4 位）"})
                return
            with LOCK:
                state["ha_user"] = username
            log(f"管理员账号已创建: {username}")
            self._json({"ok": True})
        elif path == "/api/wizard/apply":
            if body.get("xiaomi_user"):
                log(f"小米账号待绑定: {body['xiaomi_user'][:4]}****")
            threading.Thread(target=_apply_worker, args=(body,), daemon=True).start()
            self._json({"ok": True})
        elif path == "/api/finish":
            with LOCK:
                state["setup_done"] = True
            self._json({"ok": True})
        elif path == "/api/ha/config/config_entries/flow":
            # 模拟小米 Miot 配置流：账号密码 → 选服务器 → 成功
            self._json({
                "type": "form", "flow_id": "demo-flow-1", "title": "小米账号",
                "step": {"type": "form", "step_id": "user", "data_schema": [
                    {"name": "user", "required": True},
                    {"name": "password", "type": "password", "required": True},
                ]},
            })
        elif path.startswith("/api/ha/config/config_entries/flow/"):
            payload = body or {}
            if "server" not in payload:
                self._json({
                    "type": "form", "flow_id": "demo-flow-1", "title": "小米账号",
                    "step": {"type": "form", "step_id": "server", "data_schema": [
                        {"name": "server", "type": "select", "required": True,
                         "options": [{"value": "cn", "label": "中国大陆"},
                                     {"value": "de", "label": "德国"}]},
                    ]},
                })
            else:
                self._json({"type": "create_entry", "title": "我的米家", "version": 1,
                            "result": {"entry_id": "demo"}})
        else:
            self._send(404, '{"ok":false}')


def main():
    reset_state()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"EasyHA 演示服务器: http://127.0.0.1:{PORT}   (面板: /panel  重置: /api/demo/reset)", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
