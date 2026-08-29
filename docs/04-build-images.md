# 04 · 镜像构建指南

## 路线 B：定制镜像（推荐，开箱即零配置）

### 本机构建

在 Linux 上（ARM64 原生最简单；x86_64 需 `qemu-user-static` + `binfmt-support`）：

```bash
cd build/rpi-image
sudo ./build.sh                                  # 默认 raspberrypi4-64
MACHINE=raspberrypi5-64 sudo ./build.sh          # 换机型
ADDON_IMAGE_TAR=$PWD/easy-setup-aarch64.tar \
  sudo -E ./build.sh                             # 预置插件镜像（离线可用）
```

产物：`out/easyha-raspberrypi4-64.img.xz`，用树莓派 Imager / balenaEtcher 烧录即可。

### build.sh 做了什么

| 步骤 | 内容 |
|---|---|
| 1-2 | 下载 Raspberry Pi OS Lite arm64 并 loop 挂载（首启自动扩容由系统负责） |
| 3 | apt 换阿里云源、主机名 `easyha`、时区 `Asia/Shanghai` |
| 4 | 拷入引导层：`firstboot.sh` + `preportal/`（复用插件同款向导页面）+ systemd 单元 |
| 5 | chroot 安装 docker（Aliyun 脚本 + registry-mirrors）、avahi、dnsmasq、python3-qrcode，写 `/etc/pip.conf` |
| 6 | 安装 os-agent + homeassistant-supervised（debconf 非交互选机型） |
| 7 | 预置中国优化 `configuration.yaml`、预注册插件仓库 |
| 8 | 可选预置 easy-setup 插件镜像 tar（`docker load` 兜底） |

### CI 构建

`.github/workflows/build-rpi-image.yml` 使用 GitHub 免费 ARM64 runner（ubuntu-24.04-arm），
push 到 `main`（或手动 dispatch）自动产出 Artifact。发布 Release 时附上 `.img.xz`。

### 版本钉扎（发布前必做）

`build.sh` 顶部的变量请按发布时的最新版钉住：
`IMG_URL`（树莓派系统）、`OS_AGENT_DEB`、`SUPERVISED_DEB`（HA os-agent / supervised-installer 的 release）。

## 路线 A：官方 HAOS 用户

不需要构建镜像。把本仓库发布到 GitHub（或 Gitee 镜像），用户在插件商店添加仓库 URL，
安装「EasyHA 一键配置」。这是唯一的手工步骤，之后全自动化。

## 路线 C：源码构建深度定制 HAOS（实验性）

> **针对 H618 量产盒子的具体定制层已经落地**：machine 目标文件（defconfig / 内核片段 /
> U-Boot / DTS / SPL 布局）、系统级配网服务（复用路线 B 的 preportal）、AIC8801 驱动包、
> 量产 WiFi 芯片选型，全部在 [`build/haos-h618/`](../build/haos-h618/README.md)。

若一定要"HAOS 原生镜像 + 全部中国源"，需 fork `home-assistant/operating-system`
（Buildroot 工程）做三层补丁：

1. **包层**：`package/` 下新增 `dnsmasq`（宿主侧 shared DNS）、`avahi`、`qrcode` 相关依赖，
   在 board 配置里 enable NetworkManager 的 AP 支持。
2. **中国源层**：Buildroot 的 `make` 下载回退设置（`BR2_BACKUP_SITE` 指向国内镜像聚合站，
   如 mirrors.tuna 的 buildroot 镜像），并对 buildroot 的 default mirror 列表做替换。
3. **预装层**：把 easy-setup 镜像 tar 与仓库注册信息放进 `/mnt/data` 种子 overlay
   （HAOS 数据分区首次格式化时展开），Supervisor 启动后即识别已注册仓库与已下载镜像。

构建入口见 `.github/workflows/build-haos.yml`（默认注释，磁盘/时长成本高，仅产品化时使用）。

## 发布清单（路线 B 产品化）

- [ ] `build.sh` 版本钉扎 + 真机烧录回归（配网/回连/向导/面板）
- [ ] easy-setup 插件镜像已预置（`ADDON_IMAGE_TAR`）或首启联网可拉取
- [ ] 机身/说明书印二维码 `http://easyha.local` + 热点名 `EasyHA-Setup`
- [ ] 默认密码与免登录策略复核（`trusted_lan_login` 默认开启，面向家用）
- [ ] 售后兜底：长按恢复键清除 WiFi 配置（NM `connection delete`）→ 重新进入配网
