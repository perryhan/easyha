# HAOS 底座定制 · 全志 H618 盒子（EasyHA 路线 C）

> **路线定案（2026-08-29）**：冬瓜 fork 不采用（授权拿不到），**正式路线 = fork 官方
> `home-assistant/operating-system` + 自建 `h618_box` machine（全部走主线 U-Boot/内核）**。
> WiFi 测试期用板上 AIC8801（USB 形态，驱动集成由另一任务负责），量产换主线模组。
> 手板（192.168.3.152）现跑冬瓜 HAOS 18.1，作为**实测参照**（不使用其源码），
> 实勘证据见 [BOARD-FINDINGS.md](BOARD-FINDINGS.md) 与 board-info-dump*.txt。

## 从参照系统继承的事实（降低自建风险，不抄源码）

| 事实 | 对自建 machine 的意义 |
|---|---|
| 板子是 **H618 PCDN 公版盒子**（4G DDR3 + 128G Foresee eMMC + RTL8211F 千兆 + AIC8801 USB WiFi） | DTS 以主线 zero3 为基座覆盖公版差异（RTL8211F PHY、无 SDIO WiFi） |
| **参照系统的 U-Boot 就是主线 2024.01**（SPL 2024.01） | 主线 U-Boot 在这块公版上已验证可跑，选型直接钉 2024.01+ |
| 主线内核 6.6.x 可跑通 H618（参照系统内核 6.6.75-haos） | 内核版本选 6.6+ LTS，H618 平台代码无悬念 |
| 4GB 内存在该板跑通 | DRAM 配置目标：4GB；仍需按颗粒校准（见 uboot.config 的 DRAM 流程） |
| eMMC = Foresee NG2M212 128GB，HS200 | mmc2 配置按 HS200 |
| 板 DTS compatible `allwinner,pcdn`，boot 分区 uEnv.txt 的 FDT= 行切板 | 多板切换沿用同一约定（uEnv.txt） |
| 调试串口 `ttyS0,115200`；boot.scr 标准 HAOS A/B（env 在分区 9） | **U-Boot/DRAM 调试全靠串口**；A/B 回滚逻辑官方原生支持 |
| MAC 为本地随机生成（02:00:… 无硬件 OUI） | **量产 MAC 策略**：按 eMMC 序列派生本地管理地址（稳定免 OUI 费用），或购买 OUI |
| BootROM 启动顺序：**TF 卡优先于 eMMC** | **开发期用 TF 卡起我们的镜像，不动 eMMC 上的现有系统**；量产才写 eMMC |

## 开发流程（不碰现有系统）

```bash
# 1. fork 官方仓库并放入本目录 fork-files/ 下的文件（路径见下表）
git clone --recurse-submodules https://github.com/<you>/operating-system
cd operating-system
# 2. 构建（官方 Docker 构建容器，fork 自带的 CI 也可）
docker build -t hassos-builder .
docker run -it --rm --privileged -v $(pwd):/build hassos-builder bash
make h618_box        # 产物: build/output/images/hassos-h618-box.*.img.xz

# 3. 写 TF 卡，插卡开机（BootROM 优先从 TF 启动）
xzcat hassos-h618-box.*.img.xz | dd of=/dev/sdX bs=4M status=progress
# 4. 判断启动成功不需要串口：镜像会开 SSH/配网服务，插网线看 DHCP 上线即可远程接管
# 5. 打样通过后：量产镜像直接 dd 到 eMMC 覆盖现有系统
```

### 刷机方式（回答“能不能网络刷机”）

| 方式 | 阶段 | 说明 |
|---|---|---|
| **网络 dd 覆盖 eMMC** | 开发/交付 | 板子在网 + root shell（现在就有 ttyd）→ `xzcat image | dd of=/dev/mmcblk1`，重启生效。全网络，无需拆机 |
| **TF 卡引导安装器** | 量产/售后 | TF 卡放安装镜像，开机自检后从网络拉最新固件写入 eMMC；BootROM 天然 TF 优先 |
| **自有 OTA** | 量产正解 | 系统跑起来后 `ha os update` 走自有更新服务器，RAUC A/B 自动切换与回滚 |
| USB FEL 线刷 | 产线兜底 | 全志 BootROM 的 PhoenixSuit/sunxi-fel 线刷（盒子变砖的最后救援，也无需串口） |

**串口线的定位已降级**：它只在“TF 卡/网络都不起、怀疑 DRAM 参数错误”的排障场景才必需
（U-Boot 早于网络，那是唯一有输出的地方）。DRMA 参数按参照系统实测值起步，
大概率一次点亮；串口留作保险，不阻塞任何流程。

### 引脚图来源（回答“原理图是要生成 DTB 吗”）

是——原理图唯一的作用就是给 DTS 提供引脚/电压定义。**这个问题已经自己解决了**：
参照系统的 `sun50i-h618-pcdn.dtb` 就是这张“引脚图”，反编译提取后已全部回填
[我们的 DTS](fork-files/board/allwinner/h618box/sun50i-h618-easybox.dts)：
PMIC=AXP313a（dcdc3=1.356V → DDR3L）、eMMC DDR52 3.3V、RTL8211F @ EMAC0
（rgmii，rx/tx-delay 3100/700ps）、TF 卡 CD=PF6、UART0=PH0/PH1、USB 全 host。
反编译产物存档于 `pcdn-reference.dts`，另拉取了 `uboot-spl-2024.01-pcdn.bin`
（eMMC 8KB 偏移的完整启动镜像）供 DRAM 参数比对。

## 分工（含并行任务）

| 事项 | 负责 | 状态 |
|---|---|---|
| AIC8801（USB）驱动编译/模式切换 | **另一任务** | 进行中；本仓库只留集成位（[package/aic8800](fork-files/package/aic8800/)） |
| machine 目标（defconfig/U-Boot/DTS/内核片段） | 本仓库 | 模板已备，DRAM/引脚待原理图与串口实测 |
| 系统级配网 + easy-setup 预装叠加层 | 本仓库 | 已实现（[fork-files/rootfs-overlay/](fork-files/rootfs-overlay/)），复用统一向导前端 |
| 量产 WiFi 换主线模组 | 待拍板 | AP6256 / RTL8822CS / RTL8723DS / MT7921AU，见 [WIFI-CHIP-CHECKLIST.md](WIFI-CHIP-CHECKLIST.md) |
| OTA | 本仓库（产品化阶段） | fork 后把版本通道指向自有更新服务器，RAUC A/B 自带回滚 |

## fork 中要动的文件（官方真实路径，已核对）

官方结构：`buildroot-external/{board, bootloader, configs, genimage, kernel, ota,
package, patches, rootfs-overlay, scripts}`；板按 SoC 家族组织，Khadas VIM3 是
「主线 U-Boot 启动的 ARM64 SBC」的最佳参考板。

| fork 中的路径 | 内容 | 本仓库对应文件 |
|---|---|---|
| `buildroot-external/configs/h618_box_defconfig` | buildroot 机器配置（以 `khadas_vim3_defconfig` 为底改） | [fork-files/configs/h618_box_defconfig](fork-files/configs/h618_box_defconfig) |
| `buildroot-external/board/allwinner/kernel-h618.config` | 内核配置片段 | [fork-files/board/allwinner/kernel-h618.config](fork-files/board/allwinner/kernel-h618.config) |
| `buildroot-external/board/allwinner/h618box/uboot.config` | U-Boot defconfig（DRAM 参数见文件内流程） | [fork-files/board/allwinner/h618box/uboot.config](fork-files/board/allwinner/h618box/uboot.config) |
| `.../h618box/uboot-boot.ush`、`boot-env.txt`、`cmdline.txt` | 启动脚本（拷 khadas/vim3 同名文件适配 sunxi） | 文件头说明 |
| `.../h618box/image-spl-spl.cfg`、`partition-spl-spl.cfg` | SPL/genimage 布局（sunxi：SPL@TF/eMMC 8KB） | [fork-files/board/allwinner/h618box/](fork-files/board/allwinner/h618box/) |
| `.../h618box/meta`、`haos-hook.sh` | 机器元数据与构建钩子（拷 vim3 同名改字段） | 文件头说明 |
| `buildroot-external/rootfs-overlay/...` | **系统级配网服务**（Supervisor 起来前就能配网） | [fork-files/rootfs-overlay/](fork-files/rootfs-overlay/) |
| `buildroot-external/package/aic8800/` | AIC8801 驱动集成位（驱动本体由并行任务交付） | [fork-files/package/aic8800/](fork-files/package/aic8800/) |

同时把 `h618_box` 加入根 `Makefile` 的机器列表（抄 khadas_vim3 接法）。

## 风险与验证清单

| 项 | 状态 | 动作 |
|---|---|---|
| DRAM 参数（自建路线必须自己定） | ❗ 主要工作 | 起步用主线 zero3 defconfig 的 4GB 参数 → 串口实测 → 按颗粒校准；需要板子接串口 |
| 板级引脚（串口/LED/按键/WiFi REG_ON） | ❗ 需原理图 | 填 DTS 与 uboot.config 的 TODO |
| AIC8801 USB 模式切换 + AP 模式 | 由并行任务 | 本仓库按 [WIFI-CHIP-CHECKLIST.md](WIFI-CHIP-CHECKLIST.md) 验收 |
| H618 U-Boot 1.5GB 内存识别 | 已知问题，新版主线已修 | 钉新版 U-Boot；各内存规格回归 |
| 上游跟进 | 长期 | 定期 rebase 官方 dev 分支跑 CI 回归 |

## 下一步（按阻塞关系排序）

1. **接串口**（USB-TTL 到 ttyS0）——DRAM 调试与启动问题定位的前提
2. **原理图**（串口/LED/按键/WiFi 供电脚）——填 DTS/U-Boot 的 TODO
3. 等并行任务的 AIC8801 驱动模块产出 → 注入镜像做热点实测
4. WiFi 量产选型拍板（换 SDIO 主线模组 = 删 aic8800 包 + 内核片段加 brcmfmac/rtw88 + DTS 改 mmc1）
