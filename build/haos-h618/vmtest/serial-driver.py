#!/usr/bin/env python3
"""VM 串口交互驱动：登录 HAOS 控制台并运行诊断，全程输出到 stdout。"""
import socket
import sys
import time

SOCK = ("127.0.0.1", 4444)
LOG = open("/mnt/c/Users/34236/.zcode/workspace/default/easyha/build/haos-h618/vmtest/serial-session.log", "ab", buffering=0)


def say(s):
    print(s, flush=True)
    LOG.write(("\n" + s + "\n").encode())


def read_until(sock, patterns, timeout):
    buf = b""
    end = time.time() + timeout
    while time.time() < end:
        try:
            sock.settimeout(5)
            d = sock.recv(65536)
            if not d:
                say("[串口关闭]")
                return None, buf
            buf += d
            LOG.write(d)
            text = buf.decode("utf-8", "replace")
            for p in patterns:
                if p in text:
                    return p, buf
        except socket.timeout:
            continue
        except Exception as e:
            say(f"[recv err] {e}")
            return None, buf
    return None, buf


def send(sock, s):
    sock.sendall(s.encode())


def main():
    say("=== 等待 QEMU 串口就绪 ===")
    time.sleep(8)
    sock = socket.create_connection(SOCK, timeout=10)
    say("已连接串口")

    # 等登录提示（boot 可能要几分钟；先回车刷屏促出提示）
    p, _ = read_until(sock, ["login:"], 60)
    if not p:
        say("[未见到 login 提示，尝试回车唤醒]")
        send(sock, "\n")
        p, _ = read_until(sock, ["login:"], 120)
    if not p:
        say("[超时未到 login，dump 最近输出后退出]")
        sys.exit(1)

    send(sock, "root\n")
    time.sleep(3)
    send(sock, "login\n")
    time.sleep(3)
    read_until(sock, ["root@", "#"], 20)

    CMDS = [
        "echo ===PROVISION-STATUS===; systemctl status easyha-provision --no-pager | head -12",
        "echo ===PROVISION-JOURNAL===; journalctl -u easyha-provision --no-pager | tail -30",
        "echo ===DOCKER===; docker ps -a 2>/dev/null | head -8",
        "echo ===HA-ADDONS===; ha addons 2>/dev/null | grep -E 'easy|name|slug' | head -10",
        "echo ===STORE===; ha store 2>/dev/null | head -5",
        "echo ===PORTS===; ss -tlnp | grep -E ':80 |:8080|:8123|:4357'",
        "echo ===DISK===; df -h /mnt/data /tmp",
        "echo ===MARKER===; ls -la /mnt/data/easyha/ 2>/dev/null",
        "echo ===DIAG-DONE===",
    ]
    for c in CMDS:
        say(f"\n>>> {c}")
        send(sock, c + "\n")
        read_until(sock, ["===DIAG-DONE==="] if "DIAG-DONE" in c else ["> "], 45)
        time.sleep(1)

    say("\n=== 诊断完成，进入持续观察模式（每 60s 输出一次快照） ===")
    while True:
        time.sleep(60)
        try:
            sock.settimeout(3)
            d = sock.recv(65536)
            if d:
                LOG.write(d)
                text = d.decode("utf-8", "replace")
                if any(k in text for k in ("easyha", "FLASH", "error", "Error")):
                    say("[观察] " + text[-300:].replace("\n", " | "))
        except socket.timeout:
            pass
        except Exception as e:
            say(f"[观察中断] {e}")
            break


main()
