"""EasyHA 配网状态持久化。

状态存放在 /data/state.json（插件数据卷，跨重启保留）。
所有线程共享一把锁；写盘采用「临时文件 + rename」保证原子性。
"""
import json
import pathlib
import threading
import time

DATA_DIR = pathlib.Path("/data")
STATE_PATH = DATA_DIR / "state.json"
OPTIONS_PATH = DATA_DIR / "options.json"

_lock = threading.RLock()

DEFAULT_STATE = {
    "version": 1,
    "setup_done": False,          # 向导是否全部完成
    "ap": None,                   # {"ssid","psk","ip"} 当前热点信息
    "wifi": None,                 # {"ssid","ip"} 已连接的家庭 WiFi
    "ha_user": None,              # 向导中创建的管理员用户名
    "entities": None,             # 识别到的实体数量
    "steps": {},                  # 自动装机步骤: id -> {status, detail}
    "log": [],                    # 面向用户展示的滚动日志
}


def _now():
    return time.strftime("%H:%M:%S")


def load():
    with _lock:
        if STATE_PATH.exists():
            try:
                data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        else:
            data = {}
        state = dict(DEFAULT_STATE)
        state.update(data)
        return state


def save(state):
    with _lock:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = STATE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(STATE_PATH)


def update(**kwargs):
    with _lock:
        state = load()
        state.update(kwargs)
        save(state)
        return state


def log(message):
    with _lock:
        state = load()
        state["log"] = (state.get("log") or [])[-200:]
        state["log"].append(f"[{_now()}] {message}")
        save(state)
        print(f"[easyha] {message}", flush=True)


def step(step_id, status, detail=None):
    """status: pending | running | done | error"""
    with _lock:
        state = load()
        steps = state.setdefault("steps", {})
        entry = {"status": status}
        if detail:
            entry["detail"] = detail
        steps[step_id] = entry
        save(state)


def options():
    """读取插件选项（Supervisor 挂载在 /data/options.json）"""
    try:
        return json.loads(OPTIONS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
