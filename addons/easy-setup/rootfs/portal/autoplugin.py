"""EasyHA 自动装机引擎。

流程（全部幂等，可重复执行）：
  1. components  下载安装主流自定义集成（xiaomi_miot、可选 HACS），GitHub 下载自动走中国镜像回退
  2. panel       复制「易家」面板到 /config/www，深度合并 configuration.yaml（时区/免登录/panel_custom）
  3. addons      通过 Supervisor API 安装常用插件（File editor / Samba / Terminal & SSH）
  4. restart     重启 Home Assistant 并等待就绪
  5. discovery   补完官方 onboarding 步骤、统计识别到的设备实体、尝试自动接受零输入的发现流
"""
import io
import json
import pathlib
import time
import urllib.request
import zipfile

import ha_api
import state

CONFIG_DIR = pathlib.Path("/config")
WWW_TARGET = CONFIG_DIR / "www" / "easyha"
APP_SOURCE = pathlib.Path("/app")

# 主流集成下载源（仓库地址 × 中国加速前缀，多级回退）
CUSTOM_COMPONENTS = {
    "xiaomi_miot": {
        "name": "小米 Miot（小米生态设备接入）",
        "urls": ["https://github.com/al-one/hass-xiaomi-miot/archive/refs/heads/master.zip"],
        "enabled": True,
    },
    "hacs": {
        "name": "HACS（社区插件商店）",
        "urls": ["https://github.com/hacs/integration/releases/latest/download/hacs.zip"],
        "enabled": False,  # 由选项 install_hacs 控制
    },
}

STEP_IDS = ["components", "panel", "addons", "restart", "discovery"]


def _mirrors():
    mirrors = state.options().get("china_mirrors") or []
    if not any(m == "" for m in mirrors):
        mirrors.append("")
    return mirrors


def _download(url, timeout=60):
    """按中国镜像前缀逐级回退下载（前缀可为空串=直连）"""
    last_err = None
    for prefix in _mirrors():
        try:
            req = urllib.request.Request(prefix + url, headers={"User-Agent": "EasyHA/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as exc:  # noqa: BLE001 - 镜像逐个回退
            last_err = exc
            state.log(f"下载失败 {prefix or '直连'} {url[:60]}: {exc}")
    raise RuntimeError(f"所有镜像均下载失败: {url} ({last_err})")


def _extract_custom_component(zip_bytes, comp_name, target_dir):
    """从 zip 中提取组件目录；兼容两种结构：
       - 源码包： <前缀>/custom_components/<comp>/manifest.json
       - 发行包： 根目录即组件目录（hacs.zip），或 <comp>/manifest.json
    """
    import re

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        stem = None
        for n in names:
            m = re.search(rf"(?:^|/){re.escape(comp_name)}/manifest\.json$", n)
            if m:
                # m.start() 指向组件目录前的分隔符；stem 需包含组件目录本身
                cut = m.start() + 1 if m.start() > 0 else 0
                stem = n[: cut + len(comp_name) + 1]
                break
        if stem is None:
            # 回退：发行包（如 hacs.zip）根目录即组件文件
            if "manifest.json" in names:
                try:
                    domain = json.loads(zf.read("manifest.json").decode("utf-8", "replace")).get("domain")
                except Exception:
                    domain = None
                if domain in (None, comp_name):
                    stem = ""
        if stem is None:
            raise RuntimeError(f"{comp_name}: 压缩包中未找到 {comp_name}/manifest.json")
        out_dir = target_dir / comp_name
        out_dir.mkdir(parents=True, exist_ok=True)
        count = 0
        for n in names:
            if not n.startswith(stem) or n == stem:
                continue
            rel = n[len(stem):]
            if not rel:
                continue
            # stem 为空（zip 根即组件目录）时，去掉可能存在的 comp_name/ 一层前缀
            if not stem:
                if rel.startswith(comp_name + "/"):
                    rel = rel[len(comp_name) + 1:]
                elif "/" in rel:
                    continue  # 根目录的无关文件
            if not rel:
                continue
            dest = out_dir / rel
            if n.endswith("/"):
                dest.mkdir(parents=True, exist_ok=True)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(n))
            count += 1
        return count


def install_custom_components(install_hacs):
    target = CONFIG_DIR / "custom_components"
    target.mkdir(parents=True, exist_ok=True)
    plan = dict(CUSTOM_COMPONENTS)
    plan["hacs"]["enabled"] = bool(install_hacs)
    for comp, meta in plan.items():
        if not meta["enabled"]:
            continue
        if (target / comp / "manifest.json").exists():
            state.log(f"{comp} 已存在，跳过下载")
            continue
        state.log(f"开始下载安装 {meta['name']} ...")
        data = None
        for url in meta["urls"]:
            try:
                data = _download(url)
                break
            except RuntimeError:
                continue
        if data is None:
            state.log(f"{comp} 下载失败（所有源），已跳过")
            continue
        count = _extract_custom_component(data, comp, target)
        state.log(f"{comp} 安装完成（{count} 个文件）")


# ---------------------------------------------------------------- configuration.yaml

def _deep_merge(base, patch):
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _subnet_of(ip):
    """由设备 IP 推导 /24 子网，用于家庭 WiFi 免登录"""
    if not ip or ip.count(".") != 3:
        return None
    parts = ip.split(".")
    return f"{'.'.join(parts[:3])}.0/24"


def write_configuration(home_name, timezone, trusted_subnet):
    import yaml  # 延迟导入，方便单测

    config_path = CONFIG_DIR / "configuration.yaml"
    existing = {}
    if config_path.exists():
        try:
            existing = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            if not isinstance(existing, dict):
                existing = {}
        except Exception as exc:
            backup = config_path.with_suffix(".yaml.bak-easyha")
            backup.write_bytes(config_path.read_bytes())
            state.log(f"原 configuration.yaml 解析失败已备份: {exc}")
            existing = {}

    ha_existing = existing.get("homeassistant") or {}
    patch = {
        "default_config": None,
        "homeassistant": {
            "name": ha_existing.get("name") or home_name,
            "time_zone": timezone,
            "unit_system": "metric",
        },
        "ssdp": None,
        "zeroconf": None,
        "dhcp": None,
        "discovery": None,
    }
    if trusted_subnet:
        patch["http"] = {
            "server_host": "0.0.0.0",
            "trusted_networks": [trusted_subnet],
            "trusted_networks_allow_bypass_login": True,
        }
    panel = {
        "panel_custom": [{
            "name": "easyha",
            "sidebar_title": home_name,
            "sidebar_icon": "mdi:home-heart",
            "url_path": "easyha",
            "module_url": "/local/easyha/app.js",
            "config": {"language": "zh-Hans"},
        }]
    }

    merged = _deep_merge(existing, patch)
    panels = [p for p in (merged.get("panel_custom") or []) if isinstance(p, dict) and p.get("name") != "easyha"]
    panels.append(panel["panel_custom"][0])
    merged["panel_custom"] = panels

    # None 值表示“确保存在该键”
    merged = {k: ({} if v is None else v) for k, v in merged.items()}
    if merged.get("default_config") is None:
        merged["default_config"] = {}
    for key in ("ssdp", "zeroconf", "dhcp", "discovery"):
        if merged.get(key) is None:
            merged[key] = {}

    config_path.write_text(
        yaml.safe_dump(merged, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    state.log("configuration.yaml 已更新（时区/免登录/易家面板/发现能力）")


def install_panel_files():
    if not APP_SOURCE.exists():
        state.log("面板源文件缺失，跳过")
        return
    WWW_TARGET.mkdir(parents=True, exist_ok=True)
    for src in APP_SOURCE.iterdir():
        # panel_custom 的 module_url 固定为 /local/easyha/app.js
        dest_name = "app.js" if src.name == "easyha-panel.js" else src.name
        dest = WWW_TARGET / dest_name
        if src.is_file():
            dest.write_bytes(src.read_bytes())
    state.log("「易家」面板已写入 /config/www/easyha")


# ---------------------------------------------------------------- 主流程

def run(home_name=None, timezone=None, trusted_lan=True, install_hacs=True, install_addons=None, device_ip=None):
    """在后台线程执行；每一步状态写入 state['steps'] 供向导轮询"""
    opts = state.options()
    home_name = home_name or opts.get("home_name") or "易家"
    timezone = timezone or opts.get("timezone") or "Asia/Shanghai"
    install_addons = install_addons if install_addons is not None else opts.get("install_addons") or []
    install_hacs = opts.get("install_hacs", True) if install_hacs is None else install_hacs

    for step_id in STEP_IDS:
        state.step(step_id, "pending")
    state.update(entities=None)

    def do(step_id, fn):
        state.step(step_id, "running")
        try:
            fn()
            state.step(step_id, "done")
        except Exception as exc:  # noqa: BLE001 - 单步失败不中断整体
            state.step(step_id, "error", str(exc)[:300])
            state.log(f"步骤 {step_id} 失败: {exc}")

    # 1. 自定义集成
    do("components", lambda: install_custom_components(install_hacs))

    # 2. 面板文件 + configuration.yaml
    def do_panel():
        install_panel_files()
        subnet = _subnet_of(device_ip) if (trusted_lan and device_ip) else None
        write_configuration(home_name, timezone, subnet)
    do("panel", do_panel)

    # 3. 常用插件
    def do_addons():
        for slug in install_addons:
            try:
                state.log(ha_api.install_addon(slug))
                state.log(ha_api.start_addon(slug))
            except Exception as exc:
                state.log(f"插件 {slug} 安装失败（不影响其他步骤）: {exc}")
    do("addons", do_addons)

    # 4. 重启 HA 生效
    def do_restart():
        ha_api.restart_homeassistant()
        if not ha_api.wait_homeassistant():
            raise RuntimeError("重启后等待 HA 就绪超时")
        state.log("Home Assistant 已重启并就绪")
    do("restart", do_restart)

    # 5. 识别与收尾
    def do_discovery():
        _finish_onboarding()
        _count_entities()
        _auto_accept_discovered()
    do("discovery", do_discovery)

    state.update(setup_done=True)
    state.log("🎉 初始化完成！打开 http://easyha.local:8123 即可使用")


def _finish_onboarding():
    """跳过官方 onboarding 剩余步骤（用户账号已在向导中创建）"""
    try:
        status = ha_api.onboarding_status()
        if not status.get("user"):
            return  # 用户尚未创建，保留官方引导
        if not status.get("core_config"):
            ha_api.onboarding_core_config(39.9042, 116.4074, 50, "metric",
                                          state.options().get("timezone") or "Asia/Shanghai",
                                          state.options().get("home_name") or "易家")
        for step_id in ("analytics", "integrations", "dashboard"):
            if not status.get(step_id):
                try:
                    ha_api.onboarding_mark(step_id)
                except Exception:
                    pass
        state.log("官方引导流程已静默完成")
    except Exception as exc:
        state.log(f"跳过官方引导时出现问题（不影响使用）: {exc}")


def _count_entities():
    try:
        all_states = ha_api.states()
        device_domains = {"light", "switch", "fan", "climate", "cover", "media_player",
                          "sensor", "binary_sensor", "vacuum", "camera", "humidifier",
                          "water_heater", "lock", "button", "number", "select"}
        count = sum(1 for s in all_states if s.get("entity_id", "").split(".")[0] in device_domains)
        state.update(entities=count)
        state.log(f"自动识别到 {count} 个设备/实体")
    except Exception as exc:
        state.log(f"统计实体失败: {exc}")


def _auto_accept_discovered():
    """对发现的零输入配置流尝试自动接受（有输入要求的留给用户在 HA 里点）"""
    time.sleep(10)
    try:
        flows = ha_api.flow_progress()
        for flow in flows or []:
            try:
                context = flow.get("context", {}) or {}
                step = flow.get("step", {}) or {}
                if not context.get("source") in ("discovery", "zeroconf", "ssdp", "dhcp", "homekit", "usb"):
                    continue
                if step.get("type") == "form" and not (step.get("data_schema") or []):
                    ha_api.flow_submit(flow["flow_id"], {})
                    state.log(f"已自动接受发现: {flow.get('handler')}")
            except Exception:
                continue
    except Exception:
        pass
