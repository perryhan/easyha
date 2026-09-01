#!/usr/bin/env python3
"""VM 串口驱动 v2：同步登录状态机 + 诊断 + 持续观察向导门户。"""
import socket
import sys
import time
import re

SOCK = ("127.0.0.1", 4444)
LOG = open("/mnt/c/Users/34236/.zcode/workspace/default/easyha/build/haos-h618/vmtest/serial-v2.log", "ab", buffering=0)


def say(s):
    print(s, flush=True)
    LOG.write(("\n[驱动] " + s + "\n").encode())


class Serial:
    def __init__(self):
        self.buf = b""
        self.sock = None

    def connect(self, retries=12):
        for i in range(retries):
            try:
                self.sock = socket.create_connection(SOCK, timeout=10)
                say("串口已连接")
                return True
            except Exception as e:
                say(f"连接重试 {i+1}: {e}")
                time.sleep(5)
        return False

    def pump(self, seconds):
        end = time.time() + seconds
        out = b""
        while time.time() < end:
            try:
                self.sock.settimeout(1)
                d = self.sock.recv(65536)
                if not d:
                    raise ConnectionError("串口关闭")
                self.buf += d
                out += d
                LOG.write(d)
            except socket.timeout:
                continue
        return out

    def wait(self, patterns, timeout):
        end = time.time() + timeout
        while time.time() < end:
            text = re.sub(rb"\x1b\[[0-9;]*[a-zA-Z]|\x1b[()][0-9A-B]|\x1b=", b"", self.buf).decode("utf-8", "replace")
            for p in patterns:
                if re.search(p, text):
                    return p
            try:
                self.sock.settimeout(2)
                d = self.sock.recv(65536)
                if not d:
                    raise ConnectionError("串口关闭")
                self.buf += d
                LOG.write(d)
            except socket.timeout:
                continue
        return None

    def send(self, s):
        self.sock.sendall(s.encode())

    def fresh_prompt(self):
        """连发回车直到出现干净的 login 提示"""
        for attempt in range(10):
            self.buf = b""
            self.send("\n")
            p = self.wait([r"homeassistant login:", r"hassio>", r"root@homeassistant"], 25)
            if p == "homeassistant login:":
                return "login"
            if p == "hassio>":
                return "cli"
            if p == "root@homeassistant":
                return "shell"
        return None


def main():
    say("=== 驱动 v2 启动 ===")
    time.sleep(10)
    ser = Serial()
    if not ser.connect():
        sys.exit(1)
    ser.pump(5)

    state = None
    for round_i in range(6):
        state = ser.fresh_prompt()
        say(f"控制台状态(轮 {round_i+1}): {state}")
        if state:
            break
        ser.pump(20)
    if not state:
        say("[多轮未同步，继续重试中]")

    if state == "login":
        ser.send("root\n")
        p = ser.wait([r"Password:", r"hassio>", r"#"], 20)
        if p == "Password:":
            say("要求密码 → 发送空密码")
            ser.send("\n")
            ser.wait([r"hassio>", r"incorrect", r"login:"], 20)
    elif state == "shell":
        pass

    # 若仍在 login（密码错误等），重试一轮
    state = ser.fresh_prompt()
    if state == "login":
        say("重试登录: root + 空密码")
        ser.send("root\n")
        p = ser.wait([r"Password:", r"hassio>"], 20)
        if p == "Password:":
            ser.send("\n")
        ser.wait([r"hassio>", r"login:"], 20)

    state = ser.fresh_prompt()
    say(f"登录后状态: {state}")
    if state != "cli" and state != "shell":
        say("[未能进入 shell，dump 缓冲后退出]")
        sys.exit(1)

    if state == "cli":
        say("在 hassio CLI 中执行 login 进入 shell")
        ser.send("login\n")
        ser.wait([r"#"], 20)

    CMDS = [
        "systemctl status easyha-provision --no-pager 2>&1 | head -10",
        "journalctl -u easyha-provision --no-pager 2>&1 | tail -25",
        "docker ps -a 2>&1 | head -8",
        "ha addons 2>&1 | head -15",
        "ls /mnt/data/easyha/ 2>&1",
        "ss -tlnp | grep -E ':80 |:8080|:8123|:4357'",
        "df -h /mnt/data /tmp",
    ]
    for c in CMDS:
        say(f"\n>>> {c}")
        ser.buf = b""
        ser.send(c + "\n")
        ser.pump(6)
        text = ser.buf.decode("utf-8", "replace")
        text = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]|\x1b[()][0-9A-B]|\x1b=", "", text)
        say(text[:2500])

    say("\n=== 进入持续观察（向导门户由网络通道另行探测） ===")
    while True:
        time.sleep(60)
        try:
            ser.sock.settimeout(3)
            d = ser.sock.recv(65536)
            if d:
                LOG.write(d)
        except socket.timeout:
            pass
        except Exception as e:
            say(f"[观察中断] {e}")
            break


main()
