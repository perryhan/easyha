# hassos_h618-box-18.3.dev0 · 烧录与首测指南

> 云编译产物：HAOS 18.3.dev0 · machine `h618-box` · H618 PCDN 公版（4G DDR3L + 128G eMMC + RTL8211F 千兆）
> 镜像已验证：sunxi SPL@8KB（eGON.BT0 头）、MBR "Hass" 签名、HAOS 8 分区布局、xz 完整性校验通过。

## 镜像信息

| 项 | 值 |
|---|---|
| 文件 | `out/haos_h618-box-18.3.dev0.img.xz`（277 MB 压缩 / 约 900MB+ 解压后） |
| 系统 | Home Assistant OS 18.3.dev0（官方 dev 分支 + h618_box machine） |
| 内核 | Linux 6.18.48（主线） |
| U-Boot | 2026.04（主线，DDR3-1333 参数，ATF bl31 集成） |
| 内置 | 系统级配网服务（开机 30 秒出热点，无需网线）+ 中国优化配置预置 |
| WiFi | AIC8801 USB（驱动由并行任务交付后集成；当前镜像无 WiFi，配网走网口） |

## 烧录（TF 卡，不动现有系统）

**Windows**：用 [Rufus](https://rufus.ie) / [balenaEtcher](https://etcher.balena.io) 直接写入 `.img.xz`（无需解压）。

**Linux/macOS**：
```bash
xzcat haos_h618-box-18.3.dev0.img.xz | dd of=/dev/sdX bs=4M status=progress
# /dev/sdX 换成 TF 卡设备名，务必确认（lsblk），写错盘会毁数据
```

## 首测步骤（H618 公版盒子）

1. 盒子**断电**，插入 TF 卡（BootROM 优先 TF 启动，eMMC 上的冬瓜系统不受影响）
2. 接网线（首次测试先走有线验证系统可启动；WiFi 驱动尚未集成）
3. 上电，等 3~5 分钟（首次启动要初始化 data 分区、拉起 Supervisor 容器）
4. 路由器后台找新设备（hostname `homeassistant` / `hassio`），或浏览器试
   `http://homeassistant.local:8123`（也试 `http://homeassistant:8123`）
5. 起来后：向导/插件仓库 URL 填 `https://github.com/perryhan/easyha` 安装 easy-setup

## 判定与排障

| 现象 | 含义 | 动作 |
|---|---|---|
| 路由器出现新设备、:8123 可访问 | ✅ 镜像点亮成功 | 继续全流程测试（装 easy-setup → 绑小米 → 易家面板） |
| 网口灯不闪 / 5 分钟后无设备 | 可能是 DRAM 参数不匹配 | 需要串口（ttyS0 PH0/PH1 115200）看 SPL 阶段输出——这是唯一需要串口的场景 |
| 网口灯闪但无 :8123 | 内核起来了、服务有问题 | 我从 ttyd/SSH（镜像内置 dropbear）进去查 |

**测试完成后量产**：确认稳定即可 `xzcat | dd of=/dev/mmcblk1` 覆盖 eMMC（网络 dd 也行，在运行的系统上执行）。

## 已知边界（如实说明）

- DRAM 参数用的是主线 Zero2 的 DDR3 基准，公版颗粒未实测——**首次点亮有风险**，起不来就需要串口抓 SPL 日志校准（U-Boot 的 DRAM 参数调法已备好文档）
- WiFi（AIC8801 USB）驱动未集成（等并行任务交付），本镜像配网依赖网线；驱动到位后贴纸扫码全流程才完整
- 镜像 14 天后从 Actions 过期，本地 `out/` 里已有副本；正式版建议发 GitHub Release 固化
