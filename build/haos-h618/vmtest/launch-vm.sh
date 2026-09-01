#!/bin/bash
# VM 启动器（前台常驻版本）
D=/tmp/haos-vm
SRC=/mnt/c/Users/34236/.zcode/workspace/default/easyha/out/haos_generic-aarch64-18.3.dev0.img.xz
VMTEST=/mnt/c/Users/34236/.zcode/workspace/default/easyha/build/haos-h618/vmtest

mkdir -p $D
rm -rf $D/haos.img $D/serial.log $D/qemu.err
echo "=== 全新解压 ==="
xz -dkc "$SRC" > $D/haos.img
qemu-img resize -f raw $D/haos.img 8G

echo "=== 启动 QEMU ==="
nohup qemu-system-aarch64 -M virt -cpu cortex-a57 -smp 4 -m 2048 \
  -bios /usr/share/qemu-efi-aarch64/QEMU_EFI.fd \
  -drive if=none,file=$D/haos.img,format=raw,id=hd0 \
  -device virtio-blk-pci,drive=hd0 \
  -device virtio-net-pci,netdev=net0 \
  -netdev user,id=net0,hostfwd=tcp::18123-:8123,hostfwd=tcp::18080-:8080,hostfwd=tcp::14257-:4357 \
  -display none -serial tcp:127.0.0.1:4444,server=on,wait=off \
  </dev/null > $D/qemu.err 2>&1 &
sleep 5
ss -tln | grep -q 4444 || { echo "[X] QEMU 启动失败:"; cat $D/qemu.err; exit 1; }
echo "QEMU OK"

echo "=== 串口驱动 v2（前台保持会话，永不退出）==="
while true; do
  python3 $VMTEST/serial-driver-v2.py 2>&1 | tee -a $VMTEST/driver-v2.log
  echo "[驱动退出，10 秒后重启驱动]"
  sleep 10
done
