"""Supervisor / Home Assistant 官方 API 客户端。

设计原则：后端不自己实现任何业务能力，全部调用 HA 官方接口：
  - Supervisor:  http://supervisor/...        （装插件、重启 HA、插件商店）
  - HA REST:     http://supervisor/homeassistant/api/...（onboarding、配置流、状态）

认证：插件容器内自动注入 SUPERVISOR_TOKEN，对 Supervisor 和 HA API 均有效。
"""
import json
import os
import time
import urllib.error
import urllib.request

SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
SUPERVISOR_BASE = "http://supervisor"
HA_API = SUPERVISOR_BASE + "/homeassistant/api"

TIMEOUT = 30
LONG_TIMEOUT = 600


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(f"{status}: {message}")
        self.status = status
        self.message = message


def request(method, path, payload=None, base=HA_API, timeout=TIMEOUT):
    """统一 HTTP 入口。path 以 / 开头，相对 base。"""
    url = base.rstrip("/") + path
    data = None
    headers = {"Authorization": f"Bearer {SUPERVISOR_TOKEN}", "Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            if not body:
                return {}
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return {"raw": body}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise ApiError(exc.code, detail) from exc
    except urllib.error.URLError as exc:
        raise ApiError(0, str(exc.reason)) from exc


def get(path, **kw):
    return request("GET", path, **kw)


def post(path, payload=None, **kw):
    return request("POST", path, payload if payload is not None else {}, **kw)


# ---------------------------------------------------------------- Supervisor

def addon_info(slug):
    try:
        return get(f"/addons/{slug}/info", base=SUPERVISOR_BASE)
    except ApiError:
        return {}


def install_addon(slug):
    info = addon_info(slug)
    if info.get("data", {}).get("version"):
        return f"{slug} 已安装"
    post(f"/addons/{slug}/install", timeout=LONG_TIMEOUT, base=SUPERVISOR_BASE)
    return f"{slug} 安装成功"


def start_addon(slug):
    info = addon_info(slug)
    if info.get("data", {}).get("state") == "started":
        return f"{slug} 已在运行"
    post(f"/addons/{slug}/start", timeout=LONG_TIMEOUT, base=SUPERVISOR_BASE)
    return f"{slug} 已启动"


def add_store_repository(url):
    """把本仓库加入插件商店（等价于 ha store add）"""
    try:
        post("/store/repositories", {"repository": url}, base=SUPERVISOR_BASE)
        return True
    except ApiError:
        return False


def restart_homeassistant():
    post("/homeassistant/restart", timeout=LONG_TIMEOUT, base=SUPERVISOR_BASE)


def wait_homeassistant(timeout=420):
    """轮询直到 HA API 就绪"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            result = get("/")
            if isinstance(result, dict) and result.get("message"):
                return True
        except ApiError:
            pass
        time.sleep(5)
    return False


def ha_running():
    try:
        result = get("/")
        return isinstance(result, dict) and bool(result.get("message"))
    except ApiError:
        return False


# ---------------------------------------------------------------- HA onboarding

def onboarding_status():
    """返回官方 onboarding 各步骤完成情况 {user: True, ...}"""
    try:
        result = get("/onboarding")
        return {item["step"]: item.get("done", False) for item in result}
    except ApiError:
        return {}


def onboarding_create_user(name, username, password, language="zh-Hans"):
    """创建管理员账号（仅首次可用，替代官方 onboarding 第一屏）"""
    return post("/onboarding/users", {
        "name": name,
        "username": username,
        "password": password,
        "language": language,
    })


def onboarding_core_config(latitude, longitude, elevation, unit_system, time_zone, location_name):
    return post("/onboarding/core_config", {
        "latitude": latitude,
        "longitude": longitude,
        "elevation": elevation,
        "unit_system": unit_system,
        "time_zone": time_zone,
        "location_name": location_name,
    })


def onboarding_mark(step, payload=None):
    """跳过官方 onboarding 剩余步骤（analytics / integrations / dashboard）"""
    return post(f"/onboarding/{step}", payload or {})


def states():
    try:
        return get("/states")
    except ApiError:
        return []


# ---------------------------------------------------------------- 配置流（自动识别）

def flow_create(handler):
    """发起某集成的配置流，如 xiaomi_miot / homekit_bridge"""
    return post("/config/config_entries/flow", {"handler": handler})


def flow_submit(flow_id, fields=None):
    return post(f"/config/config_entries/flow/{flow_id}", fields or {})


def flow_progress():
    """列出进行中的（含 zeroconf/ssdp 发现产生的）配置流"""
    try:
        return get("/config/config_entries/flow")
    except ApiError:
        return []
