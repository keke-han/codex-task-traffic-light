#!/bin/zsh
set -e

cd "$(dirname "$0")"

LABEL="com.ss.codex-traffic-light"
PLIST_NAME="$LABEL.plist"
WATCHER_LABEL="com.ss.codex-traffic-light-watcher"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
DEST="$LAUNCH_AGENTS/$PLIST_NAME"
WATCHER_DEST="$LAUNCH_AGENTS/$WATCHER_LABEL.plist"
UID_VALUE="$(id -u)"
APP_DIR="$PWD"
SUPPORT_DIR="$HOME/Library/Application Support/CodexTrafficLight"
PYTHON_PATH="$(command -v python3)"

mkdir -p "$LAUNCH_AGENTS" "$SUPPORT_DIR"

if [ ! -x "./CodexTrafficLight" ] || [ "CodexTrafficLight.swift" -nt "CodexTrafficLight" ]; then
  ./build.command
fi

cp ./CodexTrafficLight "$SUPPORT_DIR/CodexTrafficLight"
chmod +x "$SUPPORT_DIR/CodexTrafficLight"

sed \
  -e "s#__APP_DIR__#$APP_DIR#g" \
  -e "s#__SUPPORT_DIR__#$SUPPORT_DIR#g" \
  "$PLIST_NAME.template" > "$DEST"
chmod 644 "$DEST"

sed \
  -e "s#__APP_DIR__#$APP_DIR#g" \
  -e "s#__SUPPORT_DIR__#$SUPPORT_DIR#g" \
  -e "s#__PYTHON_PATH__#$PYTHON_PATH#g" \
  "com.ss.codex-traffic-light-watcher.plist.template" > "$WATCHER_DEST"
chmod 644 "$WATCHER_DEST"

launchctl bootout "gui/$UID_VALUE/$LABEL" >/dev/null 2>&1 || true
launchctl bootout "gui/$UID_VALUE" "$DEST" >/dev/null 2>&1 || true

if ! launchctl print "gui/$UID_VALUE/$LABEL" >/dev/null 2>&1; then
  launchctl bootstrap "gui/$UID_VALUE" "$DEST"
fi
launchctl enable "gui/$UID_VALUE/$LABEL" >/dev/null 2>&1 || true
launchctl kickstart -k "gui/$UID_VALUE/$LABEL" >/dev/null 2>&1 || true

launchctl bootout "gui/$UID_VALUE/$WATCHER_LABEL" >/dev/null 2>&1 || true
launchctl bootout "gui/$UID_VALUE" "$WATCHER_DEST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$UID_VALUE" "$WATCHER_DEST"
launchctl enable "gui/$UID_VALUE/$WATCHER_LABEL" >/dev/null 2>&1 || true
launchctl kickstart -k "gui/$UID_VALUE/$WATCHER_LABEL" >/dev/null 2>&1 || true

echo "开机自启已安装：$DEST"
echo "任务状态 watcher 已安装：$WATCHER_DEST"
echo "当前服务：$LABEL"
