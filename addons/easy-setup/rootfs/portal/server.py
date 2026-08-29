"""EasyHA 一键配置 · HTTP 服务。

职责（后端只做“胶水”，业务全部走 HA/Supervisor 官方 API）：
  - 静态托管重写后的初始化向导（/www）
  - 抓取手机联网探测请求，302 跳转到配置页（captive portal）
  - 配网 API：开热点（NM D-Bus）、扫描、连接家庭 WiFi
  - 向导 API：创建管理员账号（官方 onboarding API）、启动自动装机
  - /api/ha/*  白名单转发到 HA REST API（配置流/状态/服务）
  - mDNS 注册 easyha.local；后台线程维护「无网络就开热点」
"""
import io
import json
import os
import socket
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import state
import netmgr
import ha_api
import autoplugin

WWW_DIR = Path("/www")
VERSION = "1.0.0"

PORT = int(os.environ.get("PORT", "80"))
MDNS_HOST = "easyha.local"

# 常见联网探测路径 → 全部 302 到配置页，触发手机自动弹窗
CAPTIVE_PROBES = (
    "/generate_204", "/gen_204", "/hotspot-detect.html", "/library/test/success.html",
    "/connecttest.txt", "/ncsi.txt", "/success.txt", "/kindle-wifi/wifistub.html",
    "/connectivity-check.html", "/fwlink", "/check_network_status.txt",
)

# /api/ha/* 白名单：只放行只读/配置类路径，避免门户变成全权后门
HA_RELAY_ALLOW = ("config", "states", "services", "onboarding", "template", "events")

_conn_lock = threading.Lock()
_connecting = False
_wifi_error = None
_zc = None
_zc_lock = threading.Lock()


def _option(key, default=None):
    return state.options().get(key, default)


# ------------------------------------------------------------------ mDNS

def _publish_mdns(ip):
    """注册 easyha.local（A 记录）与 http 服务；IP 变化时自动重注册"""
    global _zc
    from zeroconf import ServiceInfo, Zeroconf

    with _zc_lock:
        if _zc is not None:
            try:
                _zc.close()
            except Exception:
                pass
            _zc = None
        try:
            _zc = Zeroconf()
            info = ServiceInfo(
                "_http._tcp.local.",
                f"{MDNS_HOST.split('.')[0]}._http._tcp.local.",
                server=f"{MDNS_HOST}.",
                addresses=[socket.inet_aton(ip)],
                port=PORT,
                properties={"path": "/"},
            )
            _zc.register_service(info, allow_name_change=True)
            state.log(f"mDNS 已注册: http://{MDNS_HOST} -> {ip}")
        except Exception as exc:
            state.log(f"mDNS 注册失败（可用 IP 直连）: {exc}")


# ------------------------------------------------------------------ 后台网络管理

def _network_manager_loop():
    """每 10 秒检查一次：没网就开热点；WiFi 连上就收热点；IP 变化就重注册 mDNS"""
    published_ip = None
    while True:
        try:
            st = netmgr.status()
            connected = st.get("wifi_connected") or st.get("eth_connected")
            with _conn_lock:
                connecting = _connecting

            if connected:
                ip = st.get("wifi_ip") or st.get("eth_ip")
                if st.get("wifi_connected"):
                    state.update(wifi={"ssid": st.get("wifi_ssid"), "ip": ip})
                if st.get("ap_active") and st.get("wifi_connected"):
                    netmgr.stop_ap()
                if ip and ip != published_ip:
                    published_ip = ip
                    _publish_mdns(ip)
            elif not connecting and st.get("wifi_present"):
                if not st.get("ap_active") and _option("auto_start_ap", True):
                    ssid = _option("ap_ssid", "EasyHA-Setup")
                    psk = _option("ap_password") or None
                    state.update(ap=netmgr.start_ap(ssid, psk))
                    state.log(f"配网热点已开启: {ssid}（无网络环境）")

            if st.get("ap_active") and not connected:
                state.update(ap={"ssid": _option("ap_ssid", "EasyHA-Setup"),
                                 "psk": _option("ap_password") or "", "ip": "192.168.4.1"})
        except Exception:
            traceback.print_exc()
        time.sleep(10)


def _connect_worker(ssid, psk):
    global _connecting, _wifi_error
    with _conn_lock:
        _connecting = True
    _wifi_error = None
    try:
        state.log(f"正在连接 WiFi: {ssid}")
        netmgr.connect_home(ssid, psk)
        ok, ip = netmgr.wait_connected(60)
        if ok:
            state.log(f"WiFi 连接成功: {ssid} (IP {ip})")
            state.update(wifi={"ssid": ssid, "ip": ip}, wifi_error=None)
            netmgr.stop_ap()
        else:
            _wifi_error = "连接失败：请检查密码或信号后重试"
            state.log(_wifi_error)
            # 恢复热点
            try:
                netmgr.start_ap(_option("ap_ssid", "EasyHA-Setup"), _option("ap_password") or None)
            except Exception:
                pass
    except Exception as exc:
        _wifi_error = f"连接出错: {exc}"
        state.log(_wifi_error)
    finally:
        with _conn_lock:
            _connecting = False


# ------------------------------------------------------------------ HTTP

def _qr_svg(text, box=8):
    import qrcode
    import qrcode.image.svg
    qr = qrcode.QRCode(border=2, box_size=box, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
    # SVG 工厂按字节流写入，必须用 BytesIO
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    server_version = f"EasyHA/{VERSION}"

    def log_message(self, fmt, *args):  # 精简日志
        if "/api/" in (args[0] if args else ""):
            state.log(f"HTTP {fmt % args}")

    # ---- 基础工具 ----
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

    def _json(self, payload, code=200):
        self._send(code, json.dumps(payload, ensure_ascii=False))

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return {}

    def _redirect(self, location):
        self._send(302, b"", "text/plain", extra={"Location": location})

    def _static(self, name, ctype):
        path = WWW_DIR / name
        if not path.is_file():
            self._send(404, "not found", "text/plain")
            return
        self._send(200, path.read_bytes(), ctype)

    # ---- GET ----
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path in CAPTIVE_PROBES or path.startswith("/generate_204"):
                self._redirect("/")
                return
            if path == "/api/status":
                self._json(self._status())
                return
            if path == "/api/wifi/list":
                try:
                    self._json({"ok": True, "list": netmgr.scan()})
                except Exception as exc:
                    self._json({"ok": False, "error": str(exc), "list": []})
                return
            if path == "/api/qr":
                qs = parse_qs(parsed.query)
                text = (qs.get("text") or ["http://easyha.local:8123"])[0]
                self._send(200, _qr_svg(text), "image/svg+xml")
                return
            if path == "/api/wizard/progress":
                st = state.load()
                steps = st.get("steps") or {}
                all_done = bool(steps) and all(
                    v.get("status") == "done" for v in steps.values())
                self._json({
                    "ok": True,
                    "steps": steps,
                    "done": all_done or bool(st.get("setup_done")),
                    "setup_done": bool(st.get("setup_done")),
                    "entities": st.get("entities"),
                    "log": (st.get("log") or [])[-50:],
                })
                return
            if path.startswith("/api/ha/"):
                self._relay("GET", path[len("/api/ha/"):])
                return
            if path in ("/", "/index.html"):
                self._static("index.html", "text/html; charset=utf-8")
                return
            if path == "/wizard.js":
                self._static("wizard.js", "application/javascript; charset=utf-8")
                return
            if path == "/style.css":
                self._static("style.css", "text/css; charset=utf-8")
                return
            self._redirect("/")
        except Exception as exc:
            traceback.print_exc()
            self._json({"ok": False, "error": str(exc)}, 500)

    # ---- POST ----
    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/api/wifi/connect":
                body = self._body()
                ssid = (body.get("ssid") or "").strip()
                if not ssid:
                    self._json({"ok": False, "error": "缺少 SSID"})
                    return
                threading.Thread(target=_connect_worker, args=(ssid, body.get("psk") or ""),
                                 daemon=True).start()
                self._json({"ok": True})
                return
            if path == "/api/wizard/account":
                self._wizard_account(self._body())
                return
            if path == "/api/wizard/apply":
                self._wizard_apply(self._body())
                return
            if path == "/api/finish":
                state.update(setup_done=True)
                self._json({"ok": True})
                return
            if path.startswith("/api/ha/"):
                self._relay("POST", path[len("/api/ha/"):], self._body())
                return
            self._json({"ok": False, "error": "not found"}, 404)
        except Exception as exc:
            traceback.print_exc()
            self._json({"ok": False, "error": str(exc)}, 500)

    # ---- 端点实现 ----
    def _status(self):
        st = state.load()
        net = netmgr.status()
        if net.get("wifi_connected"):
            mode = "wifi"
        elif net.get("eth_connected"):
            mode = "ethernet"
        elif net.get("ap_active"):
            mode = "ap"
        else:
            mode = "offline"
        with _conn_lock:
            connecting = _connecting
        return {
            "ok": True,
            "version": VERSION,
            "mode": mode,
            "mdns": MDNS_HOST,
            "ha_url": f"http://{MDNS_HOST}:8123",
            "portal_url": f"http://{MDNS_HOST}",
            "ap": st.get("ap"),
            "wifi": st.get("wifi"),
            "wifi_error": _wifi_error,
            "connecting": connecting,
            "setup_done": bool(st.get("setup_done")),
            "ha_user": st.get("ha_user"),
            "entities": st.get("entities"),
            "home_name": _option("home_name", "易家"),
            "network": net,
        }

    def _wizard_account(self, body):
        name = (body.get("name") or "").strip() or "管理员"
        username = (body.get("username") or "").strip()
        password = body.get("password") or ""
        if not username or len(password) < 4:
            self._json({"ok": False, "error": "用户名或密码不符合要求（密码至少 4 位）"})
            return
        try:
            status = ha_api.onboarding_status()
            if status.get("user"):
                self._json({"ok": False, "error": "已存在管理员账号，跳过创建即可"})
                return
            if not ha_api.ha_running():
                self._json({"ok": False, "error": "Home Assistant 尚未就绪，请稍候 10 秒重试"})
                return
            ha_api.onboarding_create_user(name, username, password)
            state.update(ha_user=username)
            state.log(f"管理员账号已创建: {username}")
            self._json({"ok": True})
        except ha_api.ApiError as exc:
            self._json({"ok": False, "error": f"创建账号失败: {exc.message}"})

    def _wizard_apply(self, body):
        if body.get("xiaomi_user") and body.get("xiaomi_pass"):
            state.update(xiaomi={"user": body["xiaomi_user"], "pass": body["xiaomi_pass"]})
        threading.Thread(
            target=autoplugin.run,
            kwargs={
                "home_name": body.get("home_name") or _option("home_name", "易家"),
                "timezone": body.get("timezone") or _option("timezone", "Asia/Shanghai"),
                "trusted_lan": bool(body.get("trusted_lan", _option("trusted_lan_login", True))),
                "install_hacs": bool(body.get("install_hacs", _option("install_hacs", True))),
                "install_addons": _option("install_addons") or [],
                "device_ip": (state.load().get("wifi") or {}).get("ip") or netmgr.status().get("wifi_ip"),
            },
            daemon=True,
        ).start()
        state.log("自动装机已启动（安装组件 → 面板 → 插件 → 重启 → 识别）")
        self._json({"ok": True})

    def _relay(self, method, subpath, payload=None):
        """白名单转发到 HA REST API（供向导驱动配置流，如绑定小米账号）"""
        parts = subpath.split("/", 1)
        if not parts or parts[0] not in HA_RELAY_ALLOW:
            self._json({"ok": False, "error": "路径不在白名单内"}, 403)
            return
        try:
            result = ha_api.request(method, "/" + subpath, payload, timeout=60)
            self._json(result)
        except ha_api.ApiError as exc:
            self._json({"ok": False, "error": exc.message, "status": exc.status}, 200)


# ------------------------------------------------------------------ main

def main():
    state.log(f"EasyHA 一键配置 v{VERSION} 启动")

    # 控制台打印二维码（HDMI/串口可见），标签二维码内容固定为 http://easyha.local
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(f"http://{MDNS_HOST}")
        qr.print_ascii(invert=True, tty=False)
        print(f"\n  连接热点 [{_option('ap_ssid', 'EasyHA-Setup')}] 后，用手机扫描上方二维码\n", flush=True)
    except Exception:
        pass

    threading.Thread(target=_network_manager_loop, daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.allow_reuse_address = True
    state.log(f"配网门户就绪: http://0.0.0.0:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
