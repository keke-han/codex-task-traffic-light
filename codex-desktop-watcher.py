#!/usr/bin/env python3
"""Follow Codex rollout turn events to drive the desktop traffic light."""

import json
import re
import subprocess
import time
from pathlib import Path


HOME = Path.home()
SESSIONS = HOME / ".codex/sessions"
STATE_PATH = HOME / "Library/Application Support/CodexTrafficLight/state.json"
LOG_PATH = HOME / "Library/Application Support/CodexTrafficLight/desktop-watcher.log"
LIGHT = HOME / ".codex/bin/codex-light"
POLL_SECONDS = 0.5
STALE_FILE_SECONDS = 7 * 24 * 60 * 60
TERMINAL_EVENTS = {"task_started", "task_complete", "turn_aborted"}
THREAD_ID = re.compile(r"([0-9a-f]{8}-[0-9a-f-]{27,})\.jsonl$")


def log(message: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def read_state() -> str:
    try:
        with STATE_PATH.open(encoding="utf-8") as handle:
            return json.load(handle).get("state", "idle")
    except (OSError, ValueError, TypeError):
        return "idle"


def set_state(state: str) -> None:
    current = read_state()
    if current == state:
        return
    result = subprocess.run(
        [str(LIGHT), state],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    log(f"state {current} -> {state}" if result.returncode == 0 else f"state update failed: {state}")


def event_from_line(line: bytes):
    if not any(name.encode() in line for name in TERMINAL_EVENTS):
        return None
    try:
        record = json.loads(line)
    except (UnicodeDecodeError, ValueError):
        return None
    payload = record.get("payload", {})
    if record.get("type") != "event_msg" or payload.get("type") not in TERMINAL_EVENTS:
        return None
    if not isinstance(payload.get("turn_id"), str):
        return None
    return record.get("timestamp", ""), payload


def latest_event(path: Path, size: int):
    """Read backwards so an old, large conversation does not need a full scan."""
    with path.open("rb") as handle:
        end = size
        remainder = b""
        while end:
            start = max(0, end - 65536)
            handle.seek(start)
            parts = (handle.read(end - start) + remainder).split(b"\n")
            remainder = parts.pop(0)
            for line in reversed(parts):
                event = event_from_line(line)
                if event:
                    return event
            end = start
        return event_from_line(remainder)


def new_events(path: Path, offset: int):
    events = []
    with path.open("rb") as handle:
        handle.seek(offset)
        data = handle.read()
    last_newline = data.rfind(b"\n")
    if last_newline < 0:
        return offset, events
    for line in data[:last_newline].split(b"\n"):
        event = event_from_line(line)
        if event:
            events.append(event)
    return offset + last_newline + 1, events


def wants_reply(message: str) -> bool:
    tail = message.strip()[-500:]
    return bool(re.search(r"(?:请|需要你|麻烦你).{0,30}(?:回复|确认|选择|提供|授权|登录|上传)", tail))


class Watcher:
    def __init__(self):
        self.offsets = {}
        self.active = {}

    def files(self):
        return (p for p in SESSIONS.rglob("rollout-*.jsonl") if "保密" not in p.name)

    def start(self):
        cutoff = time.time() - STALE_FILE_SECONDS
        for path in self.files():
            match = THREAD_ID.search(path.name)
            if not match:
                continue
            try:
                attrs = path.stat()
                size = attrs.st_size
                event = latest_event(path, size) if attrs.st_mtime >= cutoff else None
            except OSError:
                continue
            self.offsets[path] = size
            if event and event[1]["type"] == "task_started":
                self.active[match.group(1)] = event[1]["turn_id"]
        log(f"watcher started; active turns={len(self.active)}")
        if self.active:
            set_state("working")

    def poll(self):
        pending = []
        for path in self.files():
            match = THREAD_ID.search(path.name)
            if not match:
                continue
            try:
                size = path.stat().st_size
                old = self.offsets.get(path, 0)
                if size < old:
                    old = 0
                if size == old:
                    continue
                offset, events = new_events(path, old)
                self.offsets[path] = offset
                pending.extend((stamp, match.group(1), payload) for stamp, payload in events)
            except OSError as error:
                log(f"read failed: {path.name}: {error}")

        completed = None
        aborted = False
        started = False
        for _, thread, payload in sorted(pending, key=lambda item: item[0]):
            kind, turn = payload["type"], payload["turn_id"]
            if kind == "task_started":
                self.active[thread] = turn
                started = True
                completed = None
                aborted = False
            elif self.active.get(thread) == turn:
                del self.active[thread]
                if kind == "task_complete":
                    completed = payload.get("last_agent_message") or ""
                else:
                    completed = None
                    aborted = True

        if self.active:
            if started or read_state() != "waiting":
                set_state("working")
        elif completed is not None:
            set_state("waiting" if wants_reply(completed) else "done")
        elif aborted:
            set_state("idle")


def main() -> None:
    watcher = Watcher()
    watcher.start()
    while True:
        try:
            watcher.poll()
        except Exception as error:
            log(f"poll failed: {error}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
