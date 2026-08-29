# EasyHA 机身贴纸（扫码配网入口）

## 文件

| 文件 | 用途 |
|---|---|
| `sticker.html` | **60×40mm 贴纸打印模板**（浏览器打开 → Ctrl+P → 另存 PDF，交付印刷） |
| `qr-wifi.svg` | 热点连接二维码（`WIFI:T:WPA;S:EasyHA-Setup;P:easyha2026;;` 标准格式） |
| `qr-portal.svg` | 控制台地址二维码（`http://easyha.local:8123`，用于说明书/双面贴纸背面） |
| `generate.py` | 生成器（改 SSID/密码后重跑 `python generate.py`） |

## 用户视角的完整流程（全程无网线）

1. 盒子通电（无网络时自动开启热点 `EasyHA-Setup`）
2. 手机相机**扫描盒底贴纸二维码** → 自动加入设备热点（系统级 WiFi 二维码，iOS 11+/Android 9+ 原生支持）
3. 配置页自动弹出（captive portal 探测 302）；未弹出则浏览器打开贴纸上的 `http://192.168.4.1`
4. 选择家里 WiFi 输密码 → 设备联网 → 手机切回家 WiFi 继续初始化向导

## 印刷规格

- 尺寸 60×40mm（二维码区 26×26mm，最小可用 20×20mm）
- 哑光防水 PVC 贴纸；二维码区禁止覆亮膜反光（影响扫码）
- 黑白即可（保留蓝 brand 块为彩色，单色印刷可整版黑）
- 热点密码按批次印刷：换批次时 `AP_PASSWORD=xxx python generate.py` 重新生成，
  并同步固件默认值（插件选项 `ap_password` / preportal `AP_PASSWORD`）
- 二维码纠错级别 M；如需更高扫码容错（曲面/磨损），generate.py 中改 `ERROR_CORRECT_Q`

## 二维码内容说明

`WIFI:T:WPA;S:<SSID>;P:<密码>;;` 是 WPA/WiFi 联盟通行的 WiFi 分享二维码格式，
iOS/Android/鸿蒙系统相机原生识别并直接连网。**贴纸不需要含设备序列号**——热点名固定，
因此一张设计稿可全批量印刷；量产如需一机一码（防蹭配网），改为随箱打印可变数据即可。

## 售后/背面（可选）

双面贴纸背面印 `qr-portal.svg` + 文案「日常访问：http://easyha.local:8123（建议添加到主屏幕）」，
并附恢复出厂说明（长按复位孔 → 热点重新出现）。
