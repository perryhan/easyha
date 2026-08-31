#!/bin/bash
# ============================================================
# EasyHA · HAOS generic_aarch64 镜像 QEMU 验证脚本（WSL2 内运行）
#
# 用法: bash qemu-verify.sh <镜像.img.xz>
# 验证内容: 镜像结构(用户端已验) → UEFI 启动 → HAOS 引导 →
#           easyha-provision 运行 → Supervisor/HA 就绪 → 向导门户
# 观测通道:
#   1. 串口日志: /tmp/haos-vm/serial.log
#   2. 端口转发: 宿主 18123→VM:8123(HA), 18080→VM:80(易家门户), 14257→VM:4357(observer)
# ============================================================
set -u
IMG_XZ="$1"
DIR=/tmp/haos-vm
mkdir -p "$DIR"

[ -f "$IMG_XZ" ] || { echo "用法: qemu-verify.sh <img.xz>"; exit 1; }

echo "=== 解压镜像 ==="
RAW="$DIR/haos.img"
[ -f "$RAW" ] || xz -dkc "$IMG_XZ" > "$RAW"
ls -la "$RAW"

echo "=== 扩容（给 data 分区自动扩展留空间） ==="
qemu-img resize -f raw "$RAW" 8G 2>/dev/null || true

echo "=== 启动 QEMU（后台，串口日志 $DIR/serial.log） ==="
rm -f "$DIR/serial.log" "$DIR/qemu.in"
mkfifo "$DIR/qemu.in" 2>/dev/null || true

nohup qemu-system-aarch64 \
  -M virt -cpu cortex-a57 -smp 4 -m 2048 \
  -bios /usr/share/qemu-efi-aarch64/QEMU_EFI.fd \
  -drive if=none,file="$RAW",format=raw,id=hd0 \
  -device virtio-blk-pci,drive=hd0 \
  -device virtio-net-pci,netdev=net0 \
  -netdev user,id=net0,hostfwd=tcp::18123-:8123,hostfwd=tcp::18080-:80,hostfwd=tcp::14257-:4357 \
  -nographic \
  < "$DIR/qemu.in" > "$DIR/serial.log" 2>&1 &
echo $! > "$DIR/qemu.pid"
exec 3>"$DIR/qemu.in"   # 保持写端打开
echo "QEMU pid=$(cat $DIR/qemu.pid)  串口日志: $DIR/serial.log"
echo "宿主侧验证端口: HA=http://<wsl-ip>:18123  门户=:18080  observer=:14257"
