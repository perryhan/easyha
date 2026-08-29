"""EasyHA 易家 · 开机配网门户（引导阶段，宿主机直跑）

在 Home Assistant 尚未就绪时，于宿主机上提供与插件版相同的向导 API：
  - 自动开热点（nmcli，shared 模式自带 DHCP/DNS）
  - /api/status、/api/wifi/list、/api/wifi/connect —— 与向导页面协议一致
  - 抓取探测请求 302 → 配置页
连上家庭 WiFi 后写入 /run/easyha/wifi.done，firstboot.sh 继续引导流程。

依赖：python3 标准库 + python3-qrcode；网络操作全部通过 nmcli 子进程。
"""
import json
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PORT = int(os.environ.get("PORT", "80"))
AP_SSID = os.environ.get("AP_SSID", "EasyHA-Setup")
# 与机身贴纸二维码一致（WIFI: 二维码携带此密码，手机扫码即连热点）
AP_PASSWORD = os.environ.get("AP_PASSWORD", "easyha2026")
DONE_FLAG = Path("/run/easyha/wifi.done")
WWW = Path("/opt/easyha/www")
WIFI_IFACE = os.environ.get("WIFI_IFACE", "wlan0")

CAPTIVE_PROBES = (
    "/generate_204", "/gen_204", "/hotspot-detect.html", "/library/test/success.html",
    "/connecttest.txt", "/ncsi.txt", "/success.txt", "/kindle-wifi/wifistub.html",
)

_lock = threading.Lock()
_state = {"connected": False, "ssid": None, "ip": None, "error": None, "connecting": False}


def sh(args, timeout=30):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def sh_ok(args, timeout=60):
    r = sh(args, timeout)
    return r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def net_status():
    """nmcli 版网络状态（与插件版字段对齐）"""
    out = {"wifi_present": False, "wifi_connected": False, "eth_connected": False,
           "wifi_ssid": None, "wifi_ip": None, "eth_ip": None, "ap_active": False}
    try:
        r = sh(["nmcli", "-t", "-f", "TYPE,STATE", "device"])
        for line in r.stdout.splitlines():
            parts = line.split(":")
            if len(parts) < 2:
                continue
            dtype, dstate = parts[0], parts[1]
            if dtype == "ethernet" and dstate == "connected":
                out["eth_connected"] = True
            if dtype == "wifi":
                out["wifi_present"] = True
                if dstate == "connected":
                    out["wifi_connected"] = True
    except Exception:
        pass
    try:
        r = sh(["nmcli", "-t", "-f", "TYPE,STATE,CONNECTION", "device"])
        for line in r.stdout.splitlines():
            parts = line.split(":")
            if len(parts) >= 3 and parts[0] == "wifi":
                if parts[2] == "easyha-ap":
                    out["ap_active"] = True
                elif parts[1] == "connected" and parts[2] != "--":
                    out["wifi_ssid"] = parts[2]
        if out["wifi_connected"]:
            ip = sh(["nmcli", "-t", "-f", "IP4.ADDRESS", "device", "show", WIFI_IFACE]).stdout
            for line in ip.splitlines():
                addr = line.strip().replace("IP4.ADDRESS[1]:", "").strip()
                if addr:
                    out["wifi_ip"] = addr.split("/")[0]
                    break
    except Exception:
        pass
    return out


def start_ap():
    args = ["nmcli", "connection", "add", "type", "wifi", "ifname", WIFI_IFACE,
            "con-name", "easyha-ap", "autoconnect", "no", "mode", "ap",
            "ssid", AP_SSID, "ipv4.method", "shared", "ipv6.method", "ignore"]
    if AP_PASSWORD:
        args += ["802-11-wireless-security.key-mgmt", "wpa-psk",
                 "802-11-wireless-security.psk", AP_PASSWORD]
    ok, msgout = sh_ok(args)
    if not ok:
        print("[preportal] 创建热点失败:", msgout, flush=True)
        return False
    ok, msgout = sh_ok(["nmcli", "connection", "up", "easyha-ap"], timeout=90)
    print("[preportal] 热点开启:", ok, msgout[:200], flush=True)
    return ok


def scan_wifi():
    try:
        sh(["nmcli", "device", "wifi", "rescan", "ifname", WIFI_IFACE], timeout=15)
    except Exception:
        pass
    time.sleep(2)
    r = sh(["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list", "ifname", WIFI_IFACE])
    seen = {}
    for line in r.stdout.splitlines():
        parts = line.split(":")
        if len(parts) < 3:
            continue
        ssid, signal, sec = parts[0], parts[1], ":".join(parts[2:])
        if not ssid or ssid in seen:
            continue
        seen[ssid] = {"ssid": ssid, "strength": int(signal or 0),
                      "security": "加密" if sec else "开放"}
    return sorted(seen.values(), key=lambda x: -x["strength"])


def connect_wifi(ssid, psk):
    """连接家庭 WiFi；NM 会持久化连接配置，重启自动回连"""
    sh(["nmcli", "connection", "delete", ssid], timeout=15)
    args = ["nmcli", "connection", "add", "type", "wifi", "ifname", WIFI_IFACE,
            "con-name", ssid, "ssid", ssid, "autoconnect", "yes"]
    if psk:
        args += ["802-11-wireless-security.key-mgmt", "wpa-psk",
                 "802-11-wireless-security.psk", psk]
    ok, msgout = sh_ok(args)
    if not ok:
        _state["error"] = "创建连接失败: " + msgout[:120]
        return False
    ok, msgout = sh_ok(["nmcli", "connection", "up", ssid], timeout=90)
    if not ok:
        _state["error"] = "连接失败，请检查密码: " + msgout[:120]
        sh(["nmcli", "connection", "delete", ssid], timeout=15)
        return False
    st = net_status()
    _state.update(connected=True, ssid=ssid, ip=st.get("wifi_ip"), error=None)
    sh(["nmcli", "connection", "down", "easyha-ap"], timeout=30)
    sh(["nmcli", "connection", "delete", "easyha-ap"], timeout=15)
    DONE_FLAG.parent.mkdir(parents=True, exist_ok=True)
    DONE_FLAG.write_text(json.dumps({"ssid": ssid, "ip": _state["ip"]}))
    print(f"[preportal] WiFi 已连接: {ssid} ({_state['ip']})", flush=True)
    return True


def qr_svg(text):
    try:
        import io
        import qrcode
        import qrcode.image.svg
        qr = qrcode.QRCode(border=2, box_size=8)
        qr.add_data(text)
        qr.make(fit=True)
        img = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
        # SVG 工厂按字节流写入，必须用 BytesIO
        buf = io.BytesIO()
        img.save(buf)
        return buf.getvalue()
    except Exception:
        return b"<svg xmlns='http://www.w3.org/2000/svg'/>"


class Handler(BaseHTTPRequestHandler):
    server_version = "EasyHAPre/1.0"

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

    def _redirect(self, loc):
        self._send(302, b"", "text/plain", extra={"Location": loc})

    def _static(self, name, ctype):
        p = WWW / name
        if not p.is_file():
            self._send(404, "not found", "text/plain")
            return
        self._send(200, p.read_bytes(), ctype)

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path in CAPTIVE_PROBES:
            self._redirect("/")
            return
        if path == "/api/status":
            st = net_status()
            mode = ("wifi" if st["wifi_connected"] else
                    "ethernet" if st["eth_connected"] else
                    "ap" if st["ap_active"] else "offline")
            self._send(200, json.dumps({
                "ok": True, "version": "bootstrap", "mode": mode,
                "mdns": "easyha.local", "ha_url": "http://easyha.local:8123",
                "portal_url": "http://easyha.local", "home_name": "易家",
                "ap": {"ssid": AP_SSID, "psk": "", "ip": "192.168.4.1"},
                "wifi": {"ssid": _state.get("ssid") or st.get("wifi_ssid"),
                         "ip": _state.get("ip") or st.get("wifi_ip")} if (st["wifi_connected"] or _state.get("connected")) else None,
                "wifi_error": _state.get("error"), "connecting": _state.get("connecting", False),
                "setup_done": False,
            }, ensure_ascii=False).encode("utf-8"))
            return
        if path == "/api/wifi/list":
            try:
                self._send(200, json.dumps({"ok": True, "list": scan_wifi()}, ensure_ascii=False).encode("utf-8"))
            except Exception as exc:
                self._send(200, json.dumps({"ok": False, "error": str(exc), "list": []}).encode("utf-8"))
            return
        if path == "/api/qr":
            text = (parse_qs(parsed.query).get("text") or ["http://easyha.local"])[0]
            self._send(200, qr_svg(text), "image/svg+xml")
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

    def do_POST(self):
        if urlparse(self.path).path != "/api/wifi/connect":
            self._send(404, json.dumps({"ok": False, "error": "not found"}).encode("utf-8"))
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except Exception:
            body = {}
        ssid = (body.get("ssid") or "").strip()
        psk = body.get("psk") or ""
        if not ssid:
            self._send(200, json.dumps({"ok": False, "error": "缺少 SSID"}).encode("utf-8"))
            return

        def worker():
            with _lock:
                _state["connecting"] = True
                try:
                    connect_wifi(ssid, psk)
                finally:
                    _state["connecting"] = False

        threading.Thread(target=worker, daemon=True).start()
        self._send(200, json.dumps({"ok": True}).encode("utf-8"))


def main():
    print(f"[preportal] 引导门户启动: 端口 {PORT}, 热点 {AP_SSID}", flush=True)
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data("http://easyha.local")
        qr.print_ascii(invert=True, tty=False)
    except Exception:
        pass
    threading.Thread(target=start_ap, daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.allow_reuse_address = True
    server.serve_forever()


if __name__ == "__main__":
    main()
