#!/bin/zsh
set -e

LABEL="com.ss.codex-traffic-light"
WATCHER_LABEL="com.ss.codex-traffic-light-watcher"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
WATCHER_PLIST="$HOME/Library/LaunchAgents/$WATCHER_LABEL.plist"
UID_VALUE="$(id -u)"

launchctl bootout "gui/$UID_VALUE/$LABEL" >/dev/null 2>&1 || true
launchctl bootout "gui/$UID_VALUE/$WATCHER_LABEL" >/dev/null 2>&1 || true
rm -f "$PLIST"
rm -f "$WATCHER_PLIST"

echo "开机自启和任务 watcher 已卸载。"
