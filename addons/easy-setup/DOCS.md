# EasyHA 一键配置（easy_setup）

## 它做什么

1. **配网**：没有有线/没有已保存的 WiFi 时，自动开启热点（默认 `EasyHA-Setup`），
   手机连上后浏览器打开任意地址都会跳到配置页（二维码印在说明书/机身标签上：`http://easyha.local`）。
2. **向导**：选家里 WiFi → 输密码 → 设备回连；创建管理员账号（替代官方 onboarding）；
   选择是否绑定小米账号；自动安装主流组件。
3. **自动装机**（全部通过 Supervisor / HA 官方 API）：
   - 下载并安装 `xiaomi_miot` 自定义集成（GitHub 下载自动走中国加速镜像，多级回退）
   - 可选安装 HACS
   - 安装常用插件：File editor（文件编辑器）、Samba、Terminal & SSH
   - 写入「易家」面板（panel_custom）到 configuration.yaml（深度合并，不破坏已有配置）
   - 重启 HA，等待就绪，统计识别到的设备/实体数量
4. **日常入口**：`http://easyha.local` → 永久落地页（打开易家面板、装到主屏幕）；侧边栏「易家」= 米家式面板。

## 选项

| 选项 | 默认 | 说明 |
|---|---|---|
| ap_ssid | EasyHA-Setup | 配网热点名 |
| ap_password | 空 | 热点密码，留空=免密 |
| auto_start_ap | true | 无网络时自动开热点 |
| china_mirrors | ghfast.top 等 | GitHub 下载加速前缀，按序回退 |
| install_hacs | true | 安装 HACS |
| install_addons | 3 个官方插件 | 需要预装的插件 slug |
| trusted_lan_login | true | 家庭 WiFi 免登录（局域网自动登录管理员） |
| home_name | 易家 | 家庭名称 |

## 二维码

- 说明书/标签二维码内容固定为 `http://easyha.local`（热点名固定，免密），
  产品化时打印一次即可，无需每台设备生成。
- 向导完成页会生成 `http://easyha.local:8123` 的二维码供保存。
