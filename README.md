# Codex Task Traffic Light

Codex 任务红绿灯 / Codex Task Traffic Light

This is an independently maintained derivative of [st44464322/codex-honglvdeng-traffic-light](https://github.com/st44464322/codex-honglvdeng-traffic-light), distributed under its MIT license. This version adds turn-aware completion tracking and a packaged macOS app.

这是一个 macOS 桌面悬浮小工具，用来显示 Codex 当前状态。

A tiny floating macOS traffic light for Codex status:

- Red: Codex is working.
- Green: work is done and ready to review, then auto-idles after 10 minutes.
- Yellow: Codex is waiting for your reply, approval, or missing input.

状态文件保存在：

```text
~/Library/Application Support/CodexTrafficLight/state.json
```

静音设置保存在：

```text
~/Library/Application Support/CodexTrafficLight/preferences.json
```

## 状态含义

- 红灯常亮：Codex 正在干活，先别催。
- 绿灯常亮：任务完成，可以验收；10 分钟后自动变为空闲。
- 黄灯先闪烁 10 秒，之后常亮：等你回复、确认、授权或补文件。
- 全暗：空闲。

## 本项目的改进

- 读取 Codex session rollout 事件，并匹配同一轮的 `turn_id` 后才确认完成。
- 并行任务全部结束后才亮绿灯；长时间无输出时保持工作状态，中断不会播放完成提示音。
- 工作中亮红灯、等待用户亮黄灯、完成亮绿灯。
- 可播放 `~/.codex/traffic-light-sounds/done.mp3` 前 10 秒；未安装自定义音频时使用系统提示音。
- `./build.command` 会生成可双击的 `CodexTaskTrafficLight.app` 和 ZIP 包。

## 提示声

- 红灯：无提示声，只亮灯。
- 绿灯：播放 `~/.codex/traffic-light-sounds/done.mp3` 前 10 秒；文件不存在时回退到 `Glass`。
- 黄灯：等待提示音 `Basso`，只提醒 10 秒，之后停止声音和闪烁。

底部左侧有一个很淡的小圆点，是隐藏静音按钮。点一下静音，再点一下恢复；静音后红灯连续提示也会停。

## 怎么打开

双击：

```text
codex-light.command
```

第一次打开会自动编译一次 Swift 原生小窗口。打开后它会悬浮在屏幕上，可以直接拖动位置。

## Install

```bash
git clone https://github.com/keke-han/codex-task-traffic-light.git
cd codex-task-traffic-light
./build.command
./install-global-command.command
./install-autostart.command
```

The autostart installer starts both the desktop light and the Codex session watcher. The generated app can also be opened directly for manual status control.

The build also creates `dist/CodexTaskTrafficLight-macOS.zip` for sharing.

Then make sure `~/.codex/bin` is in your shell path:

```bash
export PATH="$HOME/.codex/bin:$PATH"
```

## 怎么切换状态

方式一：双击悬浮灯，按顺序切换状态。

方式二：右键悬浮灯，选择状态。

方式三：双击这些快捷命令：

```text
黄灯-正在干活.command
绿灯-完成验收.command
红灯-等你回复.command
退出红绿灯.command
```

方式四：命令行控制：

```bash
./codex-light working
./codex-light done
./codex-light waiting
./codex-light idle
./codex-light quit
./codex-light status
```

如果已经执行过接入，也可以在任何目录直接用：

```bash
codex-light working
codex-light done
codex-light waiting
codex-light idle
```

## 后面接入脚本

以后任何脚本开始时加：

```bash
/完整路径/codex-light working
```

脚本完成时加：

```bash
/完整路径/codex-light done
```

需要你确认时加：

```bash
/完整路径/codex-light waiting
```

也可以直接包一层运行命令：

```bash
codex-light-run npm run build
codex-light-run python3 your_script.py
```

包装普通命令时的规则是：

- 命令开始：自动红灯。
- 命令成功：自动绿灯。
- 命令失败：按该脚本的退出状态处理。

## 当前 Codex 工作区接入

如需手动控制，也可以使用：

- 开始任务：`codex-light working`
- 完成可验收：`codex-light done`，10 分钟后自动空闲
- 等你确认：`codex-light waiting`
- 空闲：`codex-light idle`

## Codex 自动状态

桌面 watcher 读取 `~/.codex/sessions` 中的 `task_started`、`task_complete` 和 `turn_aborted`。同一轮的开始与结束 ID 匹配且没有其他正在执行的任务时，才亮绿灯并响音乐；长时间思考或工具无输出时保持红灯。中断不会响完成音。超过 7 天未更新的遗留未闭合会话不会占用当前状态。

Codex hooks 可接到：

```text
codex-light-hook
```

规则：

- `UserPromptSubmit` / `PreToolUse`：自动红灯。
- `PermissionRequest`：自动黄灯。
- `SubagentStop`：子智能体结束时保持当前灯不变，全程静默。
- `Stop`：仅记录事件，不触发绿灯；最终由 watcher 确认。绿灯保持 10 分钟后自动空闲。

参考 `codex-hooks.example.toml`，把内容加入 `~/.codex/config.toml` 后，打开 Codex 执行 `/hooks` 信任一次。

## 开机自启

安装开机自启：

```text
install-autostart.command
```

卸载开机自启：

```text
uninstall-autostart.command
```

安装后，登录 macOS 时会自动打开悬浮红绿灯。
