#!/usr/bin/env bash
# ============================================================
# EasyHA 云编译一键部署
# 前提：gh 已完成登录（gh auth status 通过）
# 动作：创建 GitHub 仓库 → 推送 → 触发 build-haos-cloud → 跟踪进度
# ============================================================
set -euo pipefail

export HTTPS_PROXY="${HTTPS_PROXY:-http://127.0.0.1:7897}"
export HTTP_PROXY="${HTTPS_PROXY}"
GH="/c/Program Files/GitHub CLI/gh.exe"
REPO_NAME="${REPO_NAME:-easyha}"

cd "$(dirname "$0")/.."

echo "==> 登录检查"
"$GH" auth status >/dev/null 2>&1 || { echo "gh 未登录，先完成设备码授权"; exit 1; }
GH_USER=$("$GH" api user -q .login)
echo "    账号: $GH_USER"

echo "==> 创建仓库 $GH_USER/$REPO_NAME（已存在则跳过）"
"$GH" repo view "$GH_USER/$REPO_NAME" >/dev/null 2>&1 || \
  "$GH" repo create "$REPO_NAME" --public --description "EasyHA 易家版 HAOS · 中国优化的 Home Assistant 发行版" >/dev/null

echo "==> 推送"
git remote remove origin 2>/dev/null || true
git remote add origin "https://github.com/$GH_USER/$REPO_NAME.git"
git push -u origin main 2>&1 | tail -2

echo "==> 触发云编译 (build-haos-cloud)"
"$GH" workflow run build-haos-cloud.yml --ref main
sleep 8
RUN_URL=$("$GH" run list --workflow=build-haos-cloud.yml --limit 1 --json url,status -q '.[0].url')
echo "    构建页: $RUN_URL"
echo "==> 完成。构建约 1~6 小时，产物在 Actions 页面的 Artifacts（hassos-h618-box）"
