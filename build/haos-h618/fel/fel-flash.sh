#!/usr/bin/env bash
# ============================================================
# EasyHA H618 · FEL 线刷脚本（在 WSL2 Ubuntu-24.04 内运行）
#
# 前置（Windows PowerShell 一次性执行，把盒子 USB 交给 WSL）：
#   盒子进 FEL 模式后（设备 1f3a:efe8）：
#     usbipd list                          # 找到 BUSID（显示 1f3a:efe8 的行）
#     usbipd bind --busid <BUSID>
#     usbipd attach --wsl --busid <BUSID>
#
# 用法（WSL 内）：
#   bash fel-flash.sh diagnose    # 只试 DRAM：先我们的 SPL，失败自动换冬瓜 SPL（确诊用）
#   bash fel-flash.sh flash       # 线刷：SPL(FEL探活) → U-Boot → UMS 暴露 eMMC 为 U 盘
# ============================================================
set -u
FELDIR="$(cd "$(dirname "$0")" && pwd)"
WSLDIR="/mnt/c/Users/34236/.zcode/workspace/default/easyha/build/haos-h618/fel"

check_dev() {
    if ! lsusb | grep -qi "1f3a:efe8"; then
        echo "[X] 未发现 FEL 设备 (1f3a:efe8)。确认：盒子已用 A-A 线连电脑并处于 FEL 模式，"
        echo "    且 PowerShell 已执行 usbipd attach。当前 lsusb："
        lsusb | head -5
        exit 1
    fi
    echo "[OK] FEL 设备在线:"; lsusb | grep -i "1f3a:efe8"
}

case "${1:-help}" in
diagnose)
    check_dev
    echo "=== [1] 试我们镜像的 SPL（DRAM 参数若正确会回到 FEL） ==="
    if timeout 30 sunxi-fel spl "$WSLDIR/our-spl.bin" 2>&1; then
        echo "[结果] 我们的 SPL 成功返回 FEL → DRAM 参数基本正确！"
        echo "       那 TF 卡启动失败另有原因（串口/网线继续排查）。"
    else
        echo "[结果] 我们的 SPL 未返回 → DRAM 参数不匹配（证实主要嫌疑）"
    fi
    echo "=== [2] 试冬瓜 SPL（本板已验证的 DRAM 参数） ==="
    if timeout 30 sunxi-fel spl "$WSLDIR/dongua-spl-proven.bin" 2>&1; then
        echo "[结果] 冬瓜 SPL 成功 → 这块板 DRAM 参数应由它提供（方案：拼接件/调参）"
    else
        echo "[结果] 冬瓜 SPL 也失败 → 检查是否真的进了 FEL（重插重短接）"
    fi
    ;;

flash)
    check_dev
    # 先跑冬瓜 SPL（DRAM 必活）→ 载入我们 U-Boot(flasher) 到 DRAM 执行
    echo "=== [1/3] 冬瓜 SPL 初始化 DRAM（本板已验证参数） ==="
    sunxi-fel spl "$WSLDIR/dongua-spl-proven.bin" || { echo "SPL 失败"; exit 1; }
    echo "=== [2/3] 载入 U-Boot 到 DRAM 并执行 ==="
    # 用 splice 件：冬瓜SPL头声明 + 我们 FIT —— sunxi-fel uboot 会解析 eGON 头分两段传输
    sunxi-fel uboot "$WSLDIR/with-spl-dongua-splice.bin" || { echo "uboot 载入失败"; exit 1; }
    echo "=== [3/3] U-Boot 运行中。此时盒子应枚举为 USB 大容量存储（eMMC） ==="
    echo "    在 Windows 磁盘管理里会出现一块 ~7.3GB 的磁盘（即 eMMC）"
    echo "    用 Rufus / 磁盘管理把 out/haos_h618-box-18.3.dev0.img 写入该磁盘即可完成线刷"
    ;;

*)
    echo "用法: bash fel-flash.sh diagnose | flash"
    ;;
esac
