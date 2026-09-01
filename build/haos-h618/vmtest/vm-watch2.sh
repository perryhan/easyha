#!/bin/bash
D=/tmp/haos-vm
LOG=/mnt/c/Users/34236/.zcode/workspace/default/easyha/build/haos-h618/vmtest/vm-status2.log
IMG=/mnt/c/Users/34236/.zcode/workspace/default/easyha/out/vmtest4/haos_generic-aarch64-18.3.dev0.img.xz
say(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

mkdir -p $D
rm -rf $D/haos.img $D/serial.log
say "全新镜像解压（干净 e2e）"
xz -dkc "$IMG" > $D/haos.img
qemu-img resize -f raw $D/haos.img 8G

start_qemu(){
  rm -f $D/serial.log
  nohup qemu-system-aarch64 -M virt -cpu cortex-a57 -smp 4 -m 2048 \
    -bios /usr/share/qemu-efi-aarch64/QEMU_EFI.fd \
    -drive if=none,file=$D/haos.img,format=raw,id=hd0 \
    -device virtio-blk-pci,drive=hd0 \
    -device virtio-net-pci,netdev=net0 \
    -netdev user,id=net0,hostfwd=tcp::18123-:8123,hostfwd=tcp::18080-:8080,hostfwd=tcp::14257-:4357 \
    -display none -serial file:$D/serial.log </dev/null > $D/qemu.err 2>&1 &
  say "QEMU 启动 pid=$!"
}

START=$(date +%s)
start_qemu
while true; do
  NOW=$(date +%s); ELAPSED=$(( (NOW-START)/60 ))
  if ! pgrep -f "qemu-system-aarch64" >/dev/null; then
    say "!! QEMU 死亡 t=${ELAPSED}min err:$(tail -1 $D/qemu.err 2>/dev/null | head -c 150)"
    [ $ELAPSED -gt 150 ] && break
    start_qemu; sleep 30; continue
  fi
  P1=$(timeout 3 curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:18123/ 2>/dev/null)
  TITLE=$(timeout 5 curl -sL --max-time 8 http://127.0.0.1:18080/ 2>/dev/null | grep -oE "<title>[^<]*" | head -1)
  say "t=${ELAPSED}min HA=$P1 门户title=[$TITLE]"
  if echo "$TITLE" | grep -q "易家"; then
    say "🎉🎉 向导门户验证通过（易家页面真实在线）— VM 全链路 e2e 成功"
    break
  fi
  [ $ELAPSED -gt 150 ] && { say "150min 窗口结束，向导未上线"; break; }
  sleep 60
done
say "watch2 退出"
