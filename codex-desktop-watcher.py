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
MAX_EVENT_LINE_BYTES = 1024 * 1024
MAX_READ_BYTES_PER_POLL = 1024 * 1024
MAX_EVENTS_PER_POLL = 1000
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
    if len(line) > MAX_EVENT_LINE_BYTES:
        return None
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
        discarding_oversized_line = False
        while end:
            start = max(0, end - 65536)
            handle.seek(start)
            parts = handle.read(end - start).split(b"\n")
            if len(parts) == 1:
                if not discarding_oversized_line:
                    remainder = parts[0] + remainder
                    if len(remainder) > MAX_EVENT_LINE_BYTES:
                        remainder = b""
                        discarding_oversized_line = True
                end = start
                continue

            if not discarding_oversized_line:
                event = event_from_line(parts[-1] + remainder)
                if event:
                    return event
            for line in reversed(parts[1:-1]):
                event = event_from_line(line)
                if event:
                    return event
            remainder = parts[0]
            discarding_oversized_line = False
            end = start
        return None if discarding_oversized_line else event_from_line(remainder)


def new_events(path: Path, offset: int, discarding_oversized_line: bool = False):
    events = []
    with path.open("rb") as handle:
        handle.seek(offset)
        data = handle.read(MAX_READ_BYTES_PER_POLL)

    if discarding_oversized_line:
        newline = data.find(b"\n")
        if newline < 0:
            return offset + len(data), events, True
        offset += newline + 1
        data = data[newline + 1 :]
        discarding_oversized_line = False

    consumed = 0
    line_count = 0
    while line_count < MAX_EVENTS_PER_POLL:
        newline = data.find(b"\n", consumed)
        if newline < 0:
            break
        line = data[consumed:newline]
        event = event_from_line(line)
        if event:
            events.append(event)
        consumed = newline + 1
        line_count += 1

    if line_count == MAX_EVENTS_PER_POLL:
        return offset + consumed, events, False

    trailing = data[consumed:]
    if len(trailing) >= MAX_EVENT_LINE_BYTES:
        return offset + len(data), events, True
    return offset + consumed, events, False


def wants_reply(message: str) -> bool:
    tail = message.strip()[-500:]
    return bool(re.search(r"(?:请|需要你|麻烦你).{0,30}(?:回复|确认|选择|提供|授权|登录|上传)", tail))


class Watcher:
    def __init__(self):
        self.offsets = {}
        self.discarding_oversized_line = set()
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
                    self.discarding_oversized_line.discard(path)
                if size == old:
                    continue
                offset, events, discarding = new_events(
                    path, old, path in self.discarding_oversized_line
                )
                self.offsets[path] = offset
                if discarding:
                    self.discarding_oversized_line.add(path)
                else:
                    self.discarding_oversized_line.discard(path)
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
