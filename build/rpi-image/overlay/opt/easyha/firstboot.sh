#!/usr/bin/env bash
# =====================================================================
# EasyHA 易家 · 首次开机引导
#  1. 有网（以太网/WiFi 已配置）则直接跳过配网
#  2. 否则：用 nmcli 在 wlan0 开热点 + 本机门户（复用易家向导页面）收集 WiFi
#  3. 联网后：等 Supervisor 就绪 → 注册插件仓库 → 安装并启动 easy-setup
# =====================================================================
set -u
LOG_TAG="easyha-firstboot"
MARKER="/var/lib/easyha/.provisioned"
DONE_FLAG="/run/easyha/wifi.done"

log() { echo "[$LOG_TAG] $(date '+%F %T') $*" | tee -a /var/log/easyha-firstboot.log; }

mkdir -p /run/easyha /var/lib/easyha
[[ -f "$MARKER" ]] && { log "已完成过引导，退出"; exit 0; }

log "设置时区"
timedatectl set-timezone Asia/Shanghai 2>/dev/null || true

# ---------- 1. 等网络（给以太网 45 秒自检） ----------
wait_ethernet() {
  for _ in $(seq 1 15); do
    if nmcli -t -f TYPE,STATE device | grep -q '^ethernet:connected$'; then
      return 0
    fi
    sleep 3
  done
  return 1
}

have_network() {
  [[ "$(nmcli networking connectivity 2>/dev/null)" == "full" ]]
}

log "等待以太网自检…"
if wait_ethernet && have_network; then
  log "检测到有线网络，跳过配网"
else
  log "无网络，启动配网热点与门户"
  rm -f "$DONE_FLAG"
  python3 /opt/easyha/preportal/server.py >> /var/log/easyha-portal.log 2>&1 &
  PORTAL_PID=$!
  log "等待用户在门户中完成 WiFi 配置（最长 40 分钟）"
  for _ in $(seq 1 800); do
    [[ -f "$DONE_FLAG" ]] && break
    have_network && break
    sleep 3
  done
  kill "$PORTAL_PID" 2>/dev/null || true
  rm -f "$DONE_FLAG"
fi

if ! have_network; then
  log "仍未联网，稍后由系统重启再次尝试"
  exit 0
fi
log "设备已联网 ✓"

# ---------- 2. 等待 Supervisor 就绪（首次要拉取大量镜像，耐心等） ----------
log "等待 Home Assistant Supervisor 就绪（最长 45 分钟）…"
ok=""
for _ in $(seq 1 180); do
  if timeout 20 ha core info >/dev/null 2>&1; then ok=1; break; fi
  sleep 15
done
if [[ -z "$ok" ]]; then
  log "Supervisor 未就绪，下次启动重试"
  exit 0
fi

# ---------- 3. 注册插件仓库并安装 easy-setup ----------
log "注册插件仓库: ${EASYHA_REPO:-https://github.com/easyha/easyha}"
for i in 1 2 3; do
  timeout 60 ha store add "${EASYHA_REPO:-https://github.com/easyha/easyha}" && break
  sleep 30
done

log "安装 easy_setup 插件…"
for i in 1 2 3; do
  if timeout 900 ha addons install easy_setup; then break; fi
  # 若已预置镜像（/opt/easyha/images/easy-setup.tar），先恢复到本地 docker
  if [[ -f /opt/easyha/images/easy-setup.tar ]]; then
    docker load -i /opt/easyha/images/easy-setup.tar || true
  fi
  sleep 30
done

log "启动 easy_setup 插件…"
timeout 120 ha addons start easy_setup || true

touch "$MARKER"
log "引导完成 ✓  用户可通过 http://easyha.local 开始初始化向导"
systemctl disable easyha-firstboot || true
