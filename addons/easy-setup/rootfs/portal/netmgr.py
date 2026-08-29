"""NetworkManager D-Bus 封装 —— EasyHA 配网的核心。

在 HAOS / Supervised 系统上，宿主机 NetworkManager 位于 system bus。
本插件通过 host_dbus + host_network 访问它，实现：

  - 查询以太网/WiFi 连接状态
  - 开启 WiFi AP 热点（ipv4.method=shared，自带 DHCP/DNS/NAT）
  - 扫描周边 WiFi
  - 连接家庭 WiFi（连接配置持久化，重启自动回连 —— 「平常也用 WiFi」）

参考: org.freedesktop.NetworkManager D-Bus API。
"""
import time

import dbus

NM = "org.freedesktop.NetworkManager"
NM_PATH = "/org/freedesktop/NetworkManager"
NM_IFACE = "org.freedesktop.NetworkManager"
DEV_IFACE = NM_IFACE + ".Device"
WIFI_IFACE = DEV_IFACE + ".Wireless"
AP_IFACE = NM_IFACE + ".AccessPoint"
IP4_IFACE = NM_IFACE + ".IP4Config"

DEV_TYPE_ETHERNET = 1
DEV_TYPE_WIFI = 2
# NM.Device.State
DEV_ACTIVATED = 100
DEV_FAILED = 120
# NM.ActiveConnection.State
AC_ACTIVATED = 2

_bus = None


def _bus_or_none():
    global _bus
    if _bus is None:
        _bus = dbus.SystemBus()
    return _bus


def _s(v):
    return dbus.String(v)


def _b(v):
    return dbus.Boolean(v)


class NetError(Exception):
    pass


def _nm():
    return _bus_or_none().get_object(NM, NM_PATH)


def _devices():
    return _nm().GetDevices(dbus_interface=NM_IFACE)


def _props(obj, iface):
    return obj.GetAll(iface, dbus_interface=dbus.PROPERTIES_IFACE)


def _prop(obj, iface, name):
    return obj.Get(iface, name, dbus_interface=dbus.PROPERTIES_IFACE)


def _split_type(devices, dtype):
    return [d for d in devices if int(_prop(d, DEV_IFACE, "DeviceType")) == dtype]


def _ip_of(dev_path):
    """从设备的 Ip4Config 取第一个 IPv4 地址字符串，取不到返回 None"""
    try:
        cfg = _prop(dbus.ObjectPath(dev_path), DEV_IFACE, "Ip4Config")
        if str(cfg) == "/" or not cfg:
            return None
        cfg_obj = _bus_or_none().get_object(NM, cfg)
        data = _prop(cfg_obj, IP4_IFACE, "AddressData")
        for item in data:
            if "address" in item:
                return str(item["address"])
    except Exception:
        pass
    return None


def status():
    """返回当前网络状态快照（永不抛异常，供状态轮询调用）"""
    out = {
        "eth_connected": False,
        "wifi_present": False,
        "wifi_connected": False,
        "wifi_ssid": None,
        "wifi_ip": None,
        "eth_ip": None,
        "ap_active": False,
    }
    try:
        for dev in _devices():
            dtype = int(_prop(dev, DEV_IFACE, "DeviceType"))
            dstate = int(_prop(dev, DEV_IFACE, "State"))
            if dtype == DEV_TYPE_ETHERNET and dstate == DEV_ACTIVATED:
                out["eth_connected"] = True
                if not out["eth_ip"]:
                    out["eth_ip"] = _ip_of(dev.object_path)
            elif dtype == DEV_TYPE_WIFI:
                out["wifi_present"] = True
                if dstate == DEV_ACTIVATED:
                    out["wifi_connected"] = True
                    try:
                        ap = _prop(dev, WIFI_IFACE, "ActiveAccessPoint")
                        if str(ap) != "/":
                            ap_obj = _bus_or_none().get_object(NM, ap)
                            ssid = bytes(_prop(ap_obj, AP_IFACE, "Ssid")).decode("utf-8", "replace")
                            out["wifi_ssid"] = ssid
                    except Exception:
                        pass
                    if not out["wifi_ip"]:
                        out["wifi_ip"] = _ip_of(dev.object_path)
                try:
                    mode = int(_prop(dev, WIFI_IFACE, "Mode"))
                    if mode == 3:  # NM 802.11Mode: 3 = AP
                        out["ap_active"] = True
                except Exception:
                    pass
    except Exception as exc:  # dbus 不可用等场景
        out["error"] = str(exc)
    return out


def enable_wifi():
    try:
        if not _prop(_nm(), NM_IFACE, "WirelessEnabled"):
            _nm().Set(NM_IFACE, "WirelessEnabled", _b(True), dbus_interface=dbus.PROPERTIES_IFACE)
            time.sleep(1.5)
    except Exception:
        pass


def wifi_device():
    devs = _split_type(_devices(), DEV_TYPE_WIFI)
    return devs[0] if devs else None


def start_ap(ssid, psk=None):
    """在 WiFi 网卡上开一个共享模式热点。

    open（免密）时不带安全配置；ipv4.method=shared 让 NM 自带
    DHCP/DNS/NAT。连接配置 autoconnect=False，不影响正常联网。
    """
    dev = wifi_device()
    if dev is None:
        raise NetError("未找到无线网卡")
    enable_wifi()

    wifi = {"mode": _s("ap"), "ssid": dbus.ByteArray(ssid.encode("utf-8")), "band": _s("bg")}
    settings = {
        "connection": {
            "type": _s("802-11-wireless"),
            "id": _s("easyha-ap"),
            "autoconnect": _b(False),
            "interface-name": _s(str(_prop(dev, DEV_IFACE, "Interface"))),
        },
        "802-11-wireless": wifi,
        "ipv4": {"method": _s("shared")},
        "ipv6": {"method": _s("ignore")},
    }
    if psk:
        settings["802-11-wireless-security"] = {"key-mgmt": _s("wpa-psk"), "psk": _s(psk)}

    # 先清理可能残留的旧热点连接，避免配置冲突
    _remove_connection("easyha-ap")

    conn_path, active_path = _nm().AddAndActivateConnection(
        dbus.Dictionary(settings, signature="sa{sv}"),
        dev.object_path,
        dbus.ObjectPath("/"),
        dbus_interface=NM_IFACE,
    )
    # 等热点激活（最多 20 秒）
    for _ in range(20):
        time.sleep(1)
        try:
            ac = _bus_or_none().get_object(NM, active_path)
            if int(_prop(ac, NM_IFACE + ".ActiveConnection", "State")) == AC_ACTIVATED:
                break
        except Exception:
            pass
    return {"ssid": ssid, "psk": psk or "", "ip": "192.168.4.1", "active": str(active_path)}


def stop_ap():
    """关闭热点（连接家庭 WiFi 成功后调用）"""
    try:
        settings_obj = _bus_or_none().get_object(NM, NM_PATH + "/Settings")
        for conn in settings_obj.ListConnections(dbus_interface=NM_IFACE + ".Settings"):
            try:
                s = conn.GetSettings(dbus_interface=NM_IFACE + ".Settings")
                if s.get("connection", {}).get("id") == "easyha-ap":
                    conn.Delete(dbus_interface=NM_IFACE + ".Settings")
            except Exception:
                pass
        for dev in _devices():
            if int(_prop(dev, DEV_IFACE, "DeviceType")) == DEV_TYPE_WIFI:
                try:
                    mode = int(_prop(dev, WIFI_IFACE, "Mode"))
                    ac = _prop(dev, DEV_IFACE, "ActiveConnection")
                    if mode == 3 and str(ac) != "/":
                        _nm().DeactivateConnection(ac, dbus_interface=NM_IFACE)
                except Exception:
                    pass
    except Exception:
        pass


def scan():
    """扫描周边 WiFi，返回 [{ssid, strength, security}]，按信号强度降序"""
    dev = wifi_device()
    if dev is None:
        return []
    enable_wifi()
    try:
        dev.RequestScan(dbus.Dictionary({}, signature="sv"), dbus_interface=WIFI_IFACE)
    except Exception:
        try:
            dev.RequestScan(dbus_interface=WIFI_IFACE)
        except Exception:
            pass
    time.sleep(1.5)

    seen = {}
    for ap in _prop(dev, WIFI_IFACE, "AccessPoints"):
        try:
            ap_obj = _bus_or_none().get_object(NM, ap)
            ssid = bytes(_prop(ap_obj, AP_IFACE, "Ssid")).decode("utf-8", "replace")
            if not ssid:
                continue
            strength = int(_prop(ap_obj, AP_IFACE, "Strength"))
            flags = int(_prop(ap_obj, AP_IFACE, "Flags"))
            wpa = int(_prop(ap_obj, AP_IFACE, "WpaFlags"))
            rsn = int(_prop(ap_obj, AP_IFACE, "RsnFlags"))
            secured = bool(flags or wpa or rsn)
            if ssid not in seen or strength > seen[ssid]["strength"]:
                seen[ssid] = {"ssid": ssid, "strength": strength, "security": "加密" if secured else "开放"}
        except Exception:
            continue
    return sorted(seen.values(), key=lambda x: -x["strength"])


def connect_home(ssid, psk):
    """连接家庭 WiFi（后台轮询由 server 驱动）。连接配置由 NM 持久化。"""
    dev = wifi_device()
    if dev is None:
        raise NetError("未找到无线网卡")
    enable_wifi()

    # 已有同名连接则直接激活，否则新建
    existing = None
    settings_obj = _bus_or_none().get_object(NM, NM_PATH + "/Settings")
    for conn in settings_obj.ListConnections(dbus_interface=NM_IFACE + ".Settings"):
        try:
            s = conn.GetSettings(dbus_interface=NM_IFACE + ".Settings")
            if s.get("connection", {}).get("id") == ssid:
                existing = conn.object_path
                break
        except Exception:
            continue

    if existing:
        active = _nm().ActivateConnection(
            dbus.ObjectPath(existing), dev.object_path, dbus.ObjectPath("/"),
            dbus_interface=NM_IFACE,
        )
        return str(active)

    wifi = {"ssid": dbus.ByteArray(ssid.encode("utf-8")), "mode": _s("infrastructure")}
    settings = {
        "connection": {"type": _s("802-11-wireless"), "id": _s(ssid), "autoconnect": _b(True)},
        "802-11-wireless": wifi,
        "ipv4": {"method": _s("auto")},
        "ipv6": {"method": _s("ignore")},
    }
    if psk:
        settings["802-11-wireless-security"] = {"key-mgmt": _s("wpa-psk"), "psk": _s(psk)}

    conn_path, active_path = _nm().AddAndActivateConnection(
        dbus.Dictionary(settings, signature="sa{sv}"),
        dev.object_path,
        dbus.ObjectPath("/"),
        dbus_interface=NM_IFACE,
    )
    return str(active_path)


def wait_connected(timeout=45):
    """等待 WiFi 激活成功。返回 (ok, ip)。"""
    dev = wifi_device()
    if dev is None:
        return False, None
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            st = int(_prop(dev, DEV_IFACE, "State"))
            if st == DEV_ACTIVATED:
                mode = int(_prop(dev, WIFI_IFACE, "Mode"))
                if mode == 2:  # infrastructure
                    return True, _ip_of(dev.object_path)
            if st == DEV_FAILED:
                return False, None
        except Exception:
            pass
        time.sleep(2)
    return False, None


def _remove_connection(conn_id):
    try:
        settings_obj = _bus_or_none().get_object(NM, NM_PATH + "/Settings")
        for conn in settings_obj.ListConnections(dbus_interface=NM_IFACE + ".Settings"):
            try:
                s = conn.GetSettings(dbus_interface=NM_IFACE + ".Settings")
                if s.get("connection", {}).get("id") == conn_id:
                    conn.Delete(dbus_interface=NM_IFACE + ".Settings")
            except Exception:
                continue
    except Exception:
        pass
