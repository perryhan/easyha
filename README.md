# EasyHA · 易家版 HAOS

面向中国普通消费者的 Home Assistant 发行版方案。目标是让 HA 的使用门槛降到米家水平：
**手机扫码 → 连上设备热点 → 选家里 WiFi → 自动装好常用插件、自动识别设备 → 打开就是「易家」面板**。

> 本仓库不改 Home Assistant 内核，全部通过 HA 官方能力实现：插件（Add-on）+ Supervisor REST API +
> HA REST/WS API + NetworkManager（D-Bus）。后端业务逻辑为零，所有数据操作都走 HA 官方接口。

## 功能对照

| 需求 | 实现方式 | 状态 |
|---|---|---|
| 镜像/依赖换成中国源 | 中国源清单 + 构建脚本（apt/pip/docker/GitHub 加速），插件下载自动多级镜像回退 | 代码完成 |
| 初始化流程简化 | 自研「配网 + 向导」页替代官方 onboarding：建号、时区、免登录、面板一次配完 | 代码完成 |
| 自动装主流插件 | `autoplugin` 调 Supervisor API 安装小米 Miot、HACS、文件编辑器等，再重启 HA | 代码完成 |
| 自动完成设备识别 | 开启 zeroconf/ssdp 发现，驱动配置流；面板自动按房间归组实体 | 代码完成 |
| 手机扫码连 WiFi 初始化 | 设备开热点（NM D-Bus）+ 门户口户 + 抓取探测请求跳转，二维码入口 `http://easyha.local` | 代码完成 |
| 平常用 WiFi、不依赖网线 | NM 持久化连接配置；首次配网后开机自动回连；支持热点兜底 | 代码完成 |
| 网页全部重写 | 「易家」向导 SPA + `panel_custom` 面板（米家式卡片、按房间分组） | 代码完成 |
| 后端尽量不自己写 | 仅一个小型配网门户，其余全部调 HA/Supervisor 官方 API | 代码完成 |

> 说明：代码层面已自洽并通过语法校验，但 **尚未在真机（树莓派/HAOS）上端到端实测**，
> 尤其是热点配网依赖 `host_dbus` 对宿主机 NetworkManager 的访问，见 `docs/05-faq.md` 的已知风险。

## 三条落地路线

| | 路线 A：官方 HAOS + 插件 | 路线 B：定制镜像 | 路线 C：HAOS fork（量产盒子，**当前主线**） |
|---|---|---|---|
| 系统 | 官方 HAOS 原镜像 | 树莓派 OS Lite + HA Supervised | 官方 HAOS fork + 自有 machine（H618 盒子） |
| 中国源 | 部分生效（插件内下载加速） | 全量生效（apt/pip/docker/ntp 全换） | 构建期全量生效 |
| 零配置程度 | 需在插件商店手动添加本仓库并装 `easy-setup` | 开箱即零配置，首次开机自动配网 | 开箱即零配置，系统级配网 + 预装 + OTA 自托管 |
| WiFi 热点配网 | 依赖 host_dbus 访问 NM（见 FAQ 风险） | 完全可控（自己管理 NM/dnsmasq/avahi） | 完全可控（配网服务直接在宿主跑） |
| 构建成本 | 无 | `build/rpi-image/build.sh`（需 Linux） | fork operating-system 加 machine（见 `build/haos-h618/`） |

## 快速开始（路线 A，现成的 HAOS 用户）

1. HA 插件商店 → 右上角 → 仓库 → 添加 `https://github.com/easyha/easyha`（换成你 fork 后的地址）。
2. 找到 **EasyHA 一键配置** 插件，安装并启动（勾选「随系统启动」「显示在侧边栏」）。
3. 手机连 WiFi 搜索热点 `EasyHA-Setup` 连接后自动弹出配置页（或浏览器打开二维码上的地址）。

## 本机演示（不需要设备）

```bash
python demo/mock_server.py     # → http://127.0.0.1:8768
```

- `http://127.0.0.1:8768/` 初始化向导全流程（配网 → 建号 → 自动装机 → 完成页）
- `http://127.0.0.1:8768/panel` 「易家」面板（模拟 hass，可交互控制设备）
- `http://127.0.0.1:8768/api/demo/reset` 重置演示
- 演示只模拟设备端行为，前端为真实交付代码；演示截图在 `demo/screenshots/`。

## 快速开始（路线 B，定制镜像）

在任意 Linux（x86_64 需 `qemu-user-static`，ARM64 原生最简单）上：

```bash
cd build/rpi-image
sudo ./build.sh          # 产出 out/easyha-rpi4-64.img.xz
```

烧录后开机即进入配网模式。CI 见 `.github/workflows/build-rpi-image.yml`（GitHub ARM64 runner）。

## 目录结构

```
easyha/
├── addons/easy-setup/        核心插件：热点配网 + 初始化向导 + 自动装机
│   ├── config.yml / Dockerfile / build.yaml
│   └── rootfs/
│       ├── run.sh
│       ├── portal/           Python 后端（配网门户 + HA/Supervisor API 网关）
│       │   ├── server.py     HTTP 服务、抓取跳转、状态机
│       │   ├── netmgr.py     NetworkManager D-Bus 封装（热点/扫描/连接）
│       │   ├── ha_api.py     Supervisor / HA REST API 客户端
│       │   ├── autoplugin.py 自动装插件、装集成、写面板、重启
│       │   └── state.py      配网状态持久化
│       ├── www/              重写后的初始化向导（原生 JS 单页）
│       └── app/              「易家」面板模块（panel_custom 加载）
├── templates/                中国优化 configuration.yaml 模板
├── build/haos-h618/          路线 C：H618 量产盒子的 HAOS 定制层（machine 目标 + 配网服务 + WiFi 选型）
│   └── fork-files/           可直接放入 operating-system fork 的文件（路径已按官方结构核对）
├── build/rpi-image/          定制镜像构建（路线 B）
├── demo/                     本机交互演示（模拟设备端 + 真实前端）
├── .github/workflows/        插件镜像 / 定制镜像 / HAOS 源码构建 CI
└── docs/                     设计文档
```

## 品牌

默认叫 **易家（EasyHA）**。热点名 `EasyHA-Setup`、mDNS 域名 `easyha.local`、面板名「易家」
都可在插件选项里改。

## 许可

MIT（本仓库自有代码）。Home Assistant / HAOS 遵循其自身的 Apache-2.0 许可。
