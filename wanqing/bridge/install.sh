#!/usr/bin/env bash
# 晚晴 — claude-bridge 安装脚本
# 将仓库内的 bridge 桥接程序部署到 ~/.rorolee/bin/，
# 让 roro 手机 App 的消息路由到 TiDB Agent Stack。
#
# 前置条件：
#   1. 已安装 rorolee 插件（~/.rorolee/bin/roro 存在，hub.sock 可用）
#   2. 已准备 ~/.rorolee/bridge.env（参考 wanqing/.env.example）
#
# 用法： bash wanqing/bridge/install.sh

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RORO_BIN_DIR="$HOME/.rorolee/bin"

echo "[install] repo dir: $REPO_DIR"

if [ ! -x "$RORO_BIN_DIR/roro" ]; then
    echo "[install] 错误：未找到 $RORO_BIN_DIR/roro —— 请先安装 rorolee 插件" >&2
    exit 1
fi

mkdir -p "$RORO_BIN_DIR"

# 1) 桥接程序
install -m 0755 "$REPO_DIR/bridge/claude-bridge" "$RORO_BIN_DIR/claude-bridge"
echo "[install] 已安装 claude-bridge -> $RORO_BIN_DIR/claude-bridge"

# 2) claude shim（如已有 roro 官方 shim 则替换）
if [ -f "$RORO_BIN_DIR/claude" ]; then
    cp "$RORO_BIN_DIR/claude" "$RORO_BIN_DIR/claude.bak.$(date +%s)"
    echo "[install] 已备份原 shim"
fi
install -m 0755 "$REPO_DIR/bridge/claude-shim" "$RORO_BIN_DIR/claude"
echo "[install] 已安装 claude shim -> $RORO_BIN_DIR/claude"

# 3) reminder-pusher（定时提醒闭环：Scheduler 触发 → MQTT 推送到 App）
install -m 0755 "$REPO_DIR/bridge/reminder-pusher" "$RORO_BIN_DIR/reminder-pusher"
install -m 0644 "$REPO_DIR/bridge/mqttws.py" "$RORO_BIN_DIR/mqttws.py"
echo "[install] 已安装 reminder-pusher + mqttws -> $RORO_BIN_DIR/"

# 4) reminder-pusher launchd 自启（开机启动 + 崩溃自拉起）
PLIST_SRC="$REPO_DIR/bridge/ai.rorolee.reminder-pusher.plist"
PLIST_DST="$HOME/Library/LaunchAgents/ai.rorolee.reminder-pusher.plist"
if [ -f "$PLIST_SRC" ]; then
    launchctl unload "$PLIST_DST" 2>/dev/null || true
    cp "$PLIST_SRC" "$PLIST_DST"
    launchctl load "$PLIST_DST"
    echo "[install] reminder-pusher 已注册 launchd 自启"
fi

# 5) family-api（家人关注 REST :8100，launchd 托管）
FAM_PLIST_SRC="$REPO_DIR/bridge/ai.rorolee.family-api.plist"
FAM_PLIST_DST="$HOME/Library/LaunchAgents/ai.rorolee.family-api.plist"
VENV_PY="$REPO_DIR/.venv/bin/python3"
if [ -f "$FAM_PLIST_SRC" ] && [ -x "$VENV_PY" ]; then
  launchctl unload "$FAM_PLIST_DST" 2>/dev/null || true
  sed -e "s|__PYTHON__|$VENV_PY|" -e "s|__REPO__|$REPO_DIR|" -e "s|__HOME__|$HOME|" \
      "$FAM_PLIST_SRC" > "$FAM_PLIST_DST"
  launchctl load "$FAM_PLIST_DST"
  echo "[install] family-api 已注册 launchd 自启（端口 8100）"
else
  echo "[install] 跳过 family-api：缺少 venv python（${VENV_PY}）"
fi

# 6) 配置检查
if [ ! -f "$HOME/.rorolee/bridge.env" ]; then
    echo "[install] 警告：缺少 ~/.rorolee/bridge.env"
    echo "          请复制 wanqing/.env.example 并填入 Agent Stack 凭证："
    echo "          cp wanqing/.env.example ~/.rorolee/bridge.env"
else
    echo "[install] 配置就绪：~/.rorolee/bridge.env"
fi

echo "[install] 完成。运行 'claude' 即可启动桥接会话；提醒推送由 reminder-pusher 自动运行。"
