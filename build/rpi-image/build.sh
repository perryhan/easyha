#!/usr/bin/env bash
# =====================================================================
# EasyHA 易家 · 定制镜像构建（路线 B）
# 基底: Raspberry Pi OS Lite (64-bit) + Home Assistant Supervised
# 产物: out/easyha-<machine>.img.xz —— 开箱即进入扫码配网，零网线依赖
#
# 运行环境: Linux（ARM64 原生最简单；x86_64 需 qemu-user-static + binfmt）
# 需要 root（losetup / mount / chroot）。
# 用法:
#   sudo ./build.sh                       # 默认 raspberrypi4-64
#   MACHINE=raspberrypi5-64 sudo ./build.sh
# 可选:
#   ADDON_IMAGE_TAR=/path/easy-setup.tar  # 预置 easy-setup 插件镜像，离线可用
# =====================================================================
set -euo pipefail

MACHINE="${MACHINE:-raspberrypi4-64}"
IMG_URL="${IMG_URL:-https://downloads.raspberrypi.com/raspios_lite_arm64_latest}"
REPO_URL="${REPO_URL:-https://github.com/easyha/easyha}"
OS_AGENT_DEB="${OS_AGENT_DEB:-https://github.com/home-assistant/os-agent/releases/latest/download/os-agent_1.6.0_linux_aarch64.deb}"
SUPERVISED_DEB="${SUPERVISED_DEB:-https://github.com/home-assistant/supervised-installer/releases/latest/download/homeassistant-supervised.deb}"

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$HERE/../.." && pwd)"
WORK="$HERE/work"
OUT="$HERE/out"
ROOTFS="$WORK/rootfs"

[[ $EUID -eq 0 ]] || { echo "请用 sudo 运行"; exit 1; }
mkdir -p "$WORK" "$OUT"

echo "==> [1/8] 下载并解压系统镜像"
IMG_XZ="$WORK/base.img.xz"
[[ -f "$IMG_XZ" ]] || curl -fL --retry 3 -o "$IMG_XZ" "$IMG_URL"
IMG="$WORK/base.img"
[[ -f "$IMG" ]] || xz -dkc "$IMG_XZ" > "$IMG"

echo "==> [2/8] 挂载镜像"
LOOP=$(losetup --find --show --partscan "$IMG")
trap 'umount_rootfs' EXIT
umount_rootfs() {
  if mountpoint -q "$ROOTFS"; then
    for d in dev proc sys run; do
      mountpoint -q "$ROOTFS/$d" && umount -R "$ROOTFS/$d" || true
    done
    umount "$ROOTFS" || true
  fi
  losetup -d "$LOOP" 2>/dev/null || true
}
BOOT="${LOOP}p1"; ROOTP="${LOOP}p2"
mkdir -p "$WORK/boot" "$ROOTFS"
mount "$BOOT" "$WORK/boot"
mount "$ROOTP" "$ROOTFS"

echo "==> [3/8] 中国源（apt）与系统基础"
R="$ROOTFS"
cat > "$R/etc/apt/sources.list.d/easyha.list" <<'EOF'
deb https://mirrors.aliyun.com/debian/ bookworm main contrib non-free non-free-firmware
deb https://mirrors.aliyun.com/debian/ bookworm-updates main contrib non-free non-free-firmware
deb https://mirrors.aliyun.com/debian-security/ bookworm-security main contrib non-free non-free-firmware
EOF
rm -f "$R/etc/apt/sources.list"
echo "easyha" > "$R/etc/hostname"
sed -i "s/127.0.1.1.*/127.0.1.1\teasyha/" "$R/etc/hosts" || echo "127.0.1.1\teasyha" >> "$R/etc/hosts"
ln -sf /usr/share/zoneinfo/Asia/Shanghai "$R/etc/localtime" 2>/dev/null || true
echo "Asia/Shanghai" > "$R/etc/timezone"

echo "==> [4/8] 复制 EasyHA 引导层"
mkdir -p "$R/opt/easyha"
cp -r "$HERE/overlay/opt/easyha/." "$R/opt/easyha/"
# 复用与插件相同的向导页面（热点引导阶段也用同一套 UI）
rm -rf "$R/opt/easyha/www"
cp -r "$ROOT_DIR/addons/easy-setup/rootfs/www" "$R/opt/easyha/www"
cp "$HERE/overlay/etc/systemd/system/easyha-firstboot.service" \
   "$R/etc/systemd/system/easyha-firstboot.service"

echo "==> [5/8] chroot 安装基础组件（docker / avahi / dnsmasq / qrcode）"
mount --bind /dev  "$R/dev"
mount --bind /proc "$R/proc"
mount --bind /sys  "$R/sys"
chroot "$R" /bin/bash -eux <<'EOS'
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  curl ca-certificates avahi-daemon dnsmasq network-manager \
  python3 python3-qrcode xz-utils parted
# Docker（阿里云安装脚本 + 镜像加速）
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh -s -- --mirror Aliyun
fi
mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<'EOJ'
{
  "registry-mirrors": ["https://docker.1ms.run", "https://docker.m.daocloud.io"],
  "log-driver": "json-file",
  "log-opts": {"max-size": "10m", "max-file": "3"}
}
EOJ
# pip 国内源（供后续维护使用）
mkdir -p /etc/pip
printf '[global]\nindex-url = https://pypi.tuna.tsinghua.edu.cn/simple\n' > /etc/pip.conf
systemctl enable docker avahi-daemon NetworkManager
EOS

echo "==> [6/8] 安装 Home Assistant Supervised"
chroot "$R" /bin/bash -eux <<EOS
# 非交互选择机型
echo "homeassistant-supervised homeassistant-supervised/machine select $MACHINE" \
  | debconf-set-selections
curl -fL --retry 3 -o /tmp/os-agent.deb "$OS_AGENT_DEB"
dpkg -i /tmp/os-agent.deb || apt-get -f install -y
curl -fL --retry 3 -o /tmp/hasup.deb "$SUPERVISED_DEB"
dpkg -i /tmp/hasup.deb || apt-get -f install -y
EOS

echo "==> [7/8] 预置 HA 配置（中国优化模板）与插件仓库"
mkdir -p "$R/usr/share/hassio/homeassistant"
cp "$ROOT_DIR/templates/configuration.yaml" "$R/usr/share/hassio/homeassistant/configuration.yaml"
cat > "$R/usr/share/hassio/homeassistant/automations.yaml" <<'EOF'
[]
EOF
cat > "$R/usr/share/hassio/homeassistant/scripts.yaml" <<'EOF'
scripts: {}
EOF
# 预置插件仓库信息，firstboot 仍会兜底再注册一次
mkdir -p "$R/usr/share/hassio/store"
cat > "$R/usr/share/hassio/store/repos.json" <<EOF
{"$REPO_URL": {"name": "EasyHA 易家", "maintainer": "EasyHA"}}
EOF

echo "==> [8/8] 可选：预置 easy-setup 插件镜像"
if [[ -n "${ADDON_IMAGE_TAR:-}" && -f "$ADDON_IMAGE_TAR" ]]; then
  mkdir -p "$R/opt/easyha/images"
  cp "$ADDON_IMAGE_TAR" "$R/opt/easyha/images/easy-setup.tar"
fi

systemctl enable easyha-firstboot --root="$R" 2>/dev/null || \
  ln -sf /etc/systemd/system/easyha-firstboot.service "$R/etc/systemd/system/multi-user.target.wants/easyha-firstboot.service"

echo "==> 打包输出"
umount_rootfs; trap - EXIT
OUT_FILE="$OUT/easyha-$MACHINE.img.xz"
xz -T0 -c "$IMG" > "$OUT_FILE"
echo "完成: $OUT_FILE"
