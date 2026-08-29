# 02 · 中国源清单与实现

原则：**构建期换源**（镜像里就带），运行期能不改系统就不改（HAOS rootfs 只读），
下载类失败自动回退。

## 汇总表

| 组件 | 国内源 | 生效位置 | 生效时机 |
|---|---|---|---|
| apt（Debian） | `mirrors.aliyun.com/debian` | 路线 B 镜像 `/etc/apt/sources.list.d/easyha.list` | 构建 + 日常 |
| pip | `pypi.tuna.tsinghua.edu.cn/simple` | 路线 B `/etc/pip.conf`；插件 Dockerfile 构建参数 | 构建 |
| Docker Registry | `docker.1ms.run`、`docker.m.daocloud.io` | 路线 B `/etc/docker/daemon.json` | 构建 |
| GitHub 下载 | `ghfast.top` → `gh-proxy.com` → `mirror.ghproxy.com` → 直连 | easy-setup 插件 `china_mirrors` 选项（多级回退） | 运行期 |
| Docker 安装脚本 | `get.docker.com --mirror Aliyun` | 路线 B build.sh | 构建 |
| 时区/NTP | `Asia/Shanghai` | 模板 configuration.yaml / firstboot | 初始化 |
| 插件镜像仓库 | ghcr.io（官方 builder 发布）；如需可再加阿里云 ACR | `build.yaml` image 字段 | 发布 |

## HAOS（路线 A）下能做到的

HAOS 系统层只读、Supervisor 拉取插件镜像的 registry（ghcr.io）不可用户配置，因此：

1. **能换的**：自定义组件下载（走插件的镜像回退列表，见 `autoplugin._download`）、
   时区/单位系统/免登录/面板（写 configuration.yaml）、插件仓库本身（发布到 ghcr，
   ghcr 在国内通常可达；如需更强的可达性，把 `build.yaml` 的 image 换成国内 registry 并在
   插件商店显示的仓库 URL 指向国内托管）。
2. **换不了的**：Supervisor 对 ghcr.io 的拉取源。缓解办法是把 easy-setup 镜像推一份到
   国内 registry，并在 `repository.json` 托管到国内可达的 Git 服务（Gitee 镜像本仓库）。
   路线 B 无此限制（daemon.json 全局生效）。

## GitHub 加速回退实现

`autoplugin._download(url)` 按插件选项 `china_mirrors` 逐个尝试
`<前缀><github 原始地址>`，任一成功即返回；全部失败才报错。
镜像失效风险高，请在发布时更新选项默认值（`addons/easy-setup/config.yml`）。

## 如何发布双源插件镜像

1. GitHub Actions（`build-addons.yml`）自动发布到 `ghcr.io/<owner>/easy-setup-{arch}`。
2. 追加一段 job：`docker pull ghcr://...` 后 `docker tag` + `docker push` 到阿里云 ACR
   （`registry.cn-hangzhou.aliyuncs.com/easyha/easy-setup-{arch}:版本`）。
3. 阿里云上再开一个「官方插件商店加速」的反代（社区常见做法），或在路线 B 镜像里
   直接预置（`ADDON_IMAGE_TAR` + `docker load`，firstboot 已内置兜底逻辑）。
