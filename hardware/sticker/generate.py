#!/usr/bin/env python3
"""EasyHA 机身贴纸生成器。

生成内容：
  - qr-wifi.svg      标准 WIFI: 二维码（手机相机扫码直接加入热点）
  - qr-portal.svg    完成后控制台地址二维码（http://easyha.local:8123）
  - sticker.html     60×40mm 贴纸打印模板（浏览器打开 → 打印为 PDF 交付印刷）

批量定制（不同批次不同热点名/密码）：改下方 SSID/PSK 后重跑本脚本。
"""
import os

import qrcode
import qrcode.image.svg

SSID = os.environ.get("AP_SSID", "EasyHA-Setup")
PSK = os.environ.get("AP_PASSWORD", "easyha2026")
PORTAL = "http://easyha.local:8123"
HERE = os.path.dirname(os.path.abspath(__file__))


def esc_wifi(s):
    r"""WIFI: 二维码转义（; , : " \ 需转义）"""
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace(":", "\\:").replace('"', '\\"')


def qr_svg(payload, box=6):
    qr = qrcode.QRCode(border=1, box_size=box, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
    # SVG 工厂按字节流写入，必须用 BytesIO
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode("utf-8")


import io  # noqa: E402
import qrcode  # noqa: E402
import qrcode.image.svg  # noqa: E402

wifi_payload = f"WIFI:T:WPA;S:{esc_wifi(SSID)};P:{esc_wifi(PSK)};;"
open(os.path.join(HERE, "qr-wifi.svg"), "w", encoding="utf-8").write(qr_svg(wifi_payload))
open(os.path.join(HERE, "qr-portal.svg"), "w", encoding="utf-8").write(qr_svg(PORTAL))

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>EasyHA 机身贴纸 60×40mm</title>
<style>
  @page {{ size: 60mm 40mm; margin: 0; }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; -webkit-print-color-adjust: exact; }}
  body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; }}
  .sticker {{
    width: 60mm; height: 40mm; background: #fff; color: #111;
    display: flex; padding: 3mm; gap: 3mm;
  }}
  .left {{ flex: 1; display: flex; flex-direction: column; justify-content: space-between; }}
  .brand {{ display: flex; align-items: center; gap: 2mm; }}
  .logo {{ width: 9mm; height: 9mm; border-radius: 2.5mm; background: #2f6bff; color: #fff;
          display: grid; place-items: center; font-size: 5.5mm; }}
  .name {{ font-size: 5mm; font-weight: 700; }}
  .name small {{ display: block; font-size: 2.2mm; font-weight: 400; color: #555; }}
  .hint {{ font-size: 3mm; line-height: 1.5; }}
  .hint b {{ color: #2f6bff; }}
  .meta {{ font-size: 2.4mm; color: #333; line-height: 1.55; }}
  .meta code {{ font-family: ui-monospace, Consolas, monospace; font-size: 2.4mm; background: #eef2ff;
               padding: 0 1mm; border-radius: 1mm; }}
  .right {{ width: 26mm; display: flex; flex-direction: column; align-items: center; gap: 1mm; }}
  .qr {{ width: 26mm; height: 26mm; }}
  .qr svg {{ width: 100%; height: 100%; }}
  .cap {{ font-size: 2.4mm; color: #555; text-align: center; }}
  @media print {{ body {{ width: 60mm; height: 40mm; }} }}
</style>
</head>
<body>
<div class="sticker">
  <div class="left">
    <div class="brand">
      <div class="logo">🏠</div>
      <div class="name">易家 <small>EasyHA · 家庭智能中心</small></div>
    </div>
    <div class="hint">首次使用：手机<b>扫右侧二维码</b><br>连接设备热点，按页面提示完成配置</div>
    <div class="meta">
      热点名称 <code>{SSID}</code><br>
      热点密码 <code>{PSK}</code><br>
      配置完成后访问 <code>{PORTAL}</code>
    </div>
  </div>
  <div class="right">
    <div class="qr">{qr_svg(wifi_payload)}</div>
    <div class="cap">扫码连接设备热点</div>
  </div>
</div>
</body>
</html>
"""
open(os.path.join(HERE, "sticker.html"), "w", encoding="utf-8").write(html)
print("生成完成:", SSID, PSK)
