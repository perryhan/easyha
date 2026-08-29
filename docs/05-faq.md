# 05 · 已知风险与 FAQ

## 风险与验证状态（重要）

本仓库代码已通过语法/结构校验，但**尚未在真机上端到端验证**。上真机前重点回归：

| 项 | 风险 | 建议 |
|---|---|---|
| HAOS 上 `host_dbus` 开热点 | 老版本 HAOS 的 polkit 可能拒绝容器调 NM `AddAndActivateConnection` | 升级到最新 HAOS；不行则路线 B（宿主自管 NM，必定可行） |
| NM shared 模式 DNS | 宿主机无 dnsmasq 时 DNS 转发缺失，手机可能不自动弹配置页 | 路线 B 已装 dnsmasq；HAOS 上用户手动打开二维码地址（不影响可用性） |
| Supervisor API 细节 | `flow_progress`（REST GET config_entries/flow）在部分版本可能 404 | 已 try/except 兜底，仅影响"自动接受发现"，不影响主流程 |
| onboarding/dashboard 步骤 | 不同 HA 版本字段有差异 | 已 try/except，失败仅影响"跳过引导"体验 |
| 中国镜像失效 | ghfast/ghproxy 类域名存活期短 | 更新 `china_mirrors` 选项默认值即可，用户侧也可在插件选项里改 |
| supervised 安装 | RPi OS 上官方定位是"supported 不保证" | 产品化建议真机长测；或评估路线 C（buildroot HAOS） |
| `ha` CLI 在 supervised 上的认证 | 个别版本需要先 `ha` 交互登录 | firstboot 已做重试 + 手册兜底（手动装 easy-setup） |

## FAQ

**Q: 为什么不直接改 HAOS 系统来换源？**
HAOS rootfs 是只读 squashfs，官方不支持运行时改系统层；换源要么在镜像构建期做（路线 C），
要么换成我们可控的宿主系统（路线 B）。插件运行期的下载（自定义组件）已内置国内镜像回退。

**Q: 免登录安全吗？**
`trusted_networks` 允许家庭 WiFi 内所有设备免登录管理员。这与米家网关等消费级产品的
默认行为一致（内网即信任）。办公/合租环境建议在插件选项里关闭 `trusted_lan_login`。

**Q: 小米设备都要绑定账号吗？**
不一定。局域网可达的（yeelight 灯、部分网关）HA 原生发现即可用；云桥类（绝大多数米家
设备）需要 `xiaomi_miot` + 小米账号，向导已内置绑定入口（通用配置流渲染器）。

**Q: 手机 App？**
控制台是 PWA：打开 `http://easyha.local:8123` → 浏览器菜单「添加到主屏幕」，图标和全屏
体验与 App 一致，无需上架应用商店。向导完成页有引导。

**Q: 换 WiFi 密码/换路由器后怎么重新配网？**
设备连不上 WiFi 会自动重开 `EasyHA-Setup` 热点，手机连上重复首次流程即可。
路线 B 还可在机身恢复孔触发 `nmcli connection delete` 强制重新配网。

**Q: 如何改品牌（易家/EasyHA）？**
热点名、域名、家庭名都在插件选项（`ap_ssid`、`home_name`）；`easyha.local` 的 mDNS 域名
在 `server.py` 的 `MDNS_HOST` 与镜像 hostname（build.sh 第 3 步）同步修改。

**Q: 用户已经用官方 HAOS 跑了一半 onboarding 怎么办？**
向导检测到 `onboarding_status().user == true` 会提示"已有账号，跳过创建"，
autoplugin 也只补装组件不覆盖已有配置（configuration.yaml 深度合并 + 备份）。
