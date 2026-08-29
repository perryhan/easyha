ARG BUILD_FROM
FROM ${BUILD_FROM}

# 依赖全部来自 Debian 官方仓库（构建期走宿主网络；发布后用户拉取镜像无需再装依赖）
#  - python3-dbus   : 经 host_dbus 访问宿主机 NetworkManager（热点/扫描/连接）
#  - python3-yaml   : 合并 configuration.yaml 不破坏用户配置
#  - python3-zeroconf: 注册 easyha.local（mDNS），手机扫码直达
#  - python3-qrcode : 生成二维码（SVG/ASCII，无需 PIL）
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-dbus \
        python3-yaml \
        python3-zeroconf \
        python3-qrcode \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY rootfs /

RUN chmod +x /run.sh && mkdir -p /data

# PORT 由 Supervisor 按声明端口注入，这里默认 80
ENV PORT=80

CMD ["/run.sh"]
