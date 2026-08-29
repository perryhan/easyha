#!/usr/bin/env bashio
set -e

bashio::log.info "EasyHA 易家 · 一键配置服务启动中..."

mkdir -p /data /share/easyha

# 把插件选项透传给 Python（Python 直接读 /data/options.json，这里只做日志摘要）
if bashio::config.has_value 'ap_ssid'; then
    bashio::log.info "热点 SSID: $(bashio::config 'ap_ssid')"
fi

exec python3 -u /portal/server.py
