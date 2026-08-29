# 开发板实勘报告（192.168.3.152 · PCDN 板）

> 勘探方式：ttyd（7681）root shell + 输出经 nc 回传取证（board-info-dump*.txt 为原始证据）。
> 勘探日期：2026-08-29。系统当时为冬瓜 HAOS 18.1。

## 系统身份（关键结论）

| 项 | 值 | 证据 |
|---|---|---|
| 系统名称 | **Home Assistant OS 18.1 · "Allwinner h618 pi box board"** | /etc/os-release |
| machine 代号 | **`h618pi`**（VARIANT_ID/OS_SUBID/board 全部一致） | os-release + `ha os info` |
| 构建来源 | **冬瓜 HAOS（waxgourd）**，BUILD_GIT=`d7838e6692`，BUILD_DATE=20260730，内核 `6.6.75-haos`（构建机 darcy@d11-compiled-haos-dev） | /etc/os-release + /proc/version |
| 中国区 | `ZONE_MODES=cn,global`，`/mnt/boot/zone` = `cn` —— 中国源在构建期已内置 | os-release + boot 分区 |
| 构建底座 | Buildroot 2022.02（HAOS 官方钉的版本）+ gcc 13.4 | /proc/version |
| 升级通道 | RAUC A/B 双分区：A=booted/good 18.1，B=inactive；`ha os info` 报 18.2 可升 | rauc.db + ha os info |

## 硬件实况

| 项 | 值 | 说明 |
|---|---|---|
| SoC | 全志 H618（`allwinner,sun50i-h618`），4×A53 | /proc/device-tree/compatible + cpuinfo |
| 板卡代号 | **PCDN**（DTS `allwinner,pcdn`，boot 用 `sun50i-h618-pcdn.dtb`） | compatible + /mnt/boot/uEnv.txt |
| 内存 | **4GB**（MemTotal ≈ 3.83 GiB）；DDR 颗粒厂商运行态不可见（需串口看 U-Boot 早期日志） | free |
| eMMC | **116.5G（128GB），颗粒型号 `G2M212`**（Foresee），HS200 | lsblk + ha os info data_disk |
| 以太网 | end0（dwmac_sun8i + realtek PHY），千兆，当前 IP 192.168.3.152 | lsmod + 网络 |
| **WiFi** | **AIC8801 在板上，但走 USB**：`a69c:5721 aicsemi Aic MSC`，当前枚举为 **U 盘模式**（AIC flash，1.7MB 固件区 sda）。系统无 aic 驱动/固件 → **无 wlan 设备**（iw dev 为空） | lsusb + dmesg |
| 串口控制台 | `console=ttyS0,115200`（抓 U-Boot/DRAM 日志要用它） | /mnt/boot/cmdline.txt |

## 冬瓜 fork 的既有能力（我们直接继承）

- **多板 H616/H618 machine 家族**：/mnt/boot/dtbs 有 9 块板
  （zero2 / zero2w / zero3 / x96-mate / t95max / cherryba-m1 / longanpi-3h / transpeed-8k618-t / pcdn），
  uEnv.txt 里 `FDT=` 一行即可切板
- **首启无线供给层**：`x88-wireless-provision.service`（WiFi/BT first-boot provisioning，
  早于 `wifi-driver-loader.service`）→ 我们的 easyha-provision 应挂在这条链后面，不与之冲突
- **冬瓜伴侣层**：websocketd/webhookd/waxgourd-wacd 服务、7681 ttyd 终端、22222 dropbear 底层 SSH
- `ha` CLI 在宿主可用且已认证（`ha addons` 正常返回）

## 对量产方案的影响

1. **不必自写 H618 machine**：冬瓜 fork 的 h618pi 已解决（DRAM/设备树/RAUC/多板）。
   量产路线 = **拿到（或谈授权）冬瓜 fork 源码 → 注入我们的 rootfs-overlay（easyha-provision +
   easy-setup 预装）→ 用自有 OTA 通道出固件**。`fork-files/` 保留作为拿不到源码时的
   自建 machine 备胎。
2. **AIC8801 是 USB 形态**：驱动需支持 USB 模式切换（MSC→WLAN），不是纯 SDIO 模组——
   选型评估按 USB 版 AIC8800D80 类处理，见 WIFI-CHIP-CHECKLIST.md 的实测项。
3. **DDR 无需操心**：容量 4GB 已确认，DRAM 初始化参数继承冬瓜的 h618pi machine（已在这块板验证）。

## 型号结论（第五批指纹，board-info-dump5.txt）

**这是 H618 PCDN 公版盒子**——PCDN 边缘计算业务（麻雀云/派通云/点心云等）批量采购的
通用方案板，业务淘汰后大量流入二手市场（闲鱼约 100~130 元/台）。compatible 里的
"pcdn" 即板厂/冬瓜对这版公板的代号。典型配置与实测完全吻合：

| 项 | 实测 | 与公版规格对照 |
|---|---|---|
| SoC | H618 4×A53 | ✅ |
| 内存 | 4GB（DDR3） | ✅ 公版 4G 配置 |
| eMMC | Foresee **NG2M212**（G2M212）128GB，2023.10 量产 | ✅ 公版 128G 配置（CID manfid 0x13 = Longsys/Foresee） |
| 网口 | Realtek PHY（realtek 驱动加载），千兆 | ✅ 公版标配 RTL8211F |
| WiFi | AIC8801 **USB 模组**（a69c:5721，U 盘模式待切） | ✅ 部分公版内置 USB WiFi |
| 接口 | USB2.0×2 / TF / HDMI / RJ45 / IR / AV（dtsi 可见） | ✅ |

**启动指纹（对自建 machine 的直接价值）**：

- U-Boot = **主线 2024.01**（SPL 2024.01, Jul 30 2026 构建）——冬瓜用的就是主线版本，
  说明 **主线 U-Boot 2024.01 在这块公版上已验证可跑**，与我们自建路线选型一致
- SPL 二进制里含主线 sunxi H616 DRAM 驱动的错误分支字符串
  （"Unsupported DRAM configuration…"）→ DRAM 初始化走的也是主线驱动（参数按颗粒定制）
- boot.scr 是 HAOS 标准 A/B 逻辑：`BOOT_ORDER`/`BOOT_A_LEFT`/`BOOT_B_LEFT` 计数回滚，
  根分区 `PARTUUID=48617373-06/-08`（"Hass"），env 存在**分区 9**
- 多板切换机制 = boot 分区 `uEnv.txt` 的 `FDT=` 行（我们移植时沿用此约定即可）
- **MAC 为本地随机生成**（02:00:…，无硬件 OUI）→ 量产需要 MAC 策略：本地管理地址
  按 eMMC 序列派生（稳定且免 OUI 费用），或购买 OUI

## 待确认（需要你/板厂）

- [x] ~~冬瓜 operating-system fork 源码能否获取~~ → **已定：拿不到授权，不采用**（2026-08-29）。
      自建 machine 为正式路线（fork-files/），参照系统仅用于实测参数对照
- [ ] AIC8801 USB 驱动 SDK（**另一任务负责驱动编译**，本仓库只留集成位）
- [ ] 量产 WiFi 最终选型（AP6256/RTL8822CS/RTL8723DS/MT7921AU 主线方案）
- [ ] 板子接串口（ttyS0）——DRAM 校准与启动调试的前提
