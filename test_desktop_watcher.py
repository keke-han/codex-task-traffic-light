import importlib.util
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "desktop_watcher", Path(__file__).with_name("codex-desktop-watcher.py")
)
watcher_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(watcher_module)


def event(kind, turn, stamp, message=""):
    payload = {"type": kind, "turn_id": turn}
    if kind == "task_complete":
        payload["last_agent_message"] = message
    return json.dumps({"timestamp": stamp, "type": "event_msg", "payload": payload}).encode() + b"\n"


class DesktopWatcherTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = "idle"
        self.transitions = []

        def set_state(value):
            if self.state != value:
                self.transitions.append(value)
                self.state = value

        for name, value in (
            ("SESSIONS", self.root),
            ("set_state", set_state),
            ("read_state", lambda: self.state),
            ("log", lambda message: None),
        ):
            p = patch.object(watcher_module, name, value)
            p.start()
            self.addCleanup(p.stop)

    def file(self, thread):
        return self.root / f"rollout-{thread}.jsonl"

    def test_long_silence_does_not_complete(self):
        p = self.file("11111111-1111-1111-1111-111111111111")
        p.write_bytes(event("task_started", "turn-a", "2026-09-30T10:00:00Z"))
        watcher = watcher_module.Watcher()
        watcher.start()
        for _ in range(20):
            watcher.poll()
        self.assertEqual(self.transitions, ["working"])
        with p.open("ab") as handle:
            handle.write(event("task_complete", "turn-a", "2026-09-30T10:30:00Z", "已完成"))
        watcher.poll()
        self.assertEqual(self.transitions, ["working", "done"])

    def test_one_finished_thread_does_not_complete_other(self):
        first = self.file("11111111-1111-1111-1111-111111111111")
        second = self.file("22222222-2222-2222-2222-222222222222")
        first.write_bytes(event("task_started", "a", "2026-09-30T10:00:00Z"))
        second.write_bytes(event("task_started", "b", "2026-09-30T10:00:01Z"))
        watcher = watcher_module.Watcher()
        watcher.start()
        with first.open("ab") as handle:
            handle.write(event("task_complete", "a", "2026-09-30T10:00:02Z"))
        watcher.poll()
        self.assertEqual(self.transitions, ["working"])
        with second.open("ab") as handle:
            handle.write(event("task_complete", "b", "2026-09-30T10:00:03Z"))
        watcher.poll()
        self.assertEqual(self.transitions, ["working", "done"])

    def test_abort_never_plays_completion(self):
        p = self.file("11111111-1111-1111-1111-111111111111")
        p.write_bytes(event("task_started", "turn-a", "2026-09-30T10:00:00Z"))
        watcher = watcher_module.Watcher()
        watcher.start()
        with p.open("ab") as handle:
            handle.write(event("turn_aborted", "turn-a", "2026-09-30T10:00:01Z"))
        watcher.poll()
        self.assertEqual(self.transitions, ["working", "idle"])

    def test_partial_line_and_old_completion_are_ignored(self):
        p = self.file("11111111-1111-1111-1111-111111111111")
        p.write_bytes(event("task_complete", "previous", "2026-09-30T09:00:00Z"))
        watcher = watcher_module.Watcher()
        watcher.start()
        self.assertEqual(self.transitions, [])
        with p.open("ab") as handle:
            handle.write(event("task_started", "current", "2026-09-30T10:00:00Z"))
        watcher.poll()
        complete = event("task_complete", "current", "2026-09-30T10:00:02Z", "完成")
        with p.open("ab") as handle:
            handle.write(complete[:-5])
        watcher.poll()
        self.assertEqual(self.transitions, ["working"])
        with p.open("ab") as handle:
            handle.write(complete[-5:])
        watcher.poll()
        self.assertEqual(self.transitions, ["working", "done"])

    def test_mismatched_completion_does_not_finish_current_turn(self):
        p = self.file("11111111-1111-1111-1111-111111111111")
        p.write_bytes(event("task_started", "current", "2026-09-30T10:00:00Z"))
        watcher = watcher_module.Watcher()
        watcher.start()
        with p.open("ab") as handle:
            handle.write(event("task_complete", "previous", "2026-09-30T10:00:02Z"))
        watcher.poll()
        self.assertEqual(self.transitions, ["working"])

    def test_stale_unclosed_session_does_not_block_new_turn(self):
        stale = self.file("11111111-1111-1111-1111-111111111111")
        current = self.file("22222222-2222-2222-2222-222222222222")
        stale.write_bytes(event("task_started", "old", "2026-05-01T10:00:00Z"))
        old_time = time.time() - watcher_module.STALE_FILE_SECONDS - 60
        os.utime(stale, (old_time, old_time))
        current.write_bytes(event("task_started", "now", "2026-09-30T10:00:00Z"))
        watcher = watcher_module.Watcher()
        watcher.start()
        self.assertEqual(len(watcher.active), 1)
        with current.open("ab") as handle:
            handle.write(event("task_complete", "now", "2026-09-30T10:00:01Z"))
        watcher.poll()
        self.assertEqual(self.transitions, ["working", "done"])

    def test_abort_after_other_completion_does_not_play_music(self):
        first = self.file("11111111-1111-1111-1111-111111111111")
        second = self.file("22222222-2222-2222-2222-222222222222")
        first.write_bytes(event("task_started", "a", "2026-09-30T10:00:00Z"))
        second.write_bytes(event("task_started", "b", "2026-09-30T10:00:01Z"))
        watcher = watcher_module.Watcher()
        watcher.start()
        with first.open("ab") as handle:
            handle.write(event("task_complete", "a", "2026-09-30T10:00:02Z"))
        with second.open("ab") as handle:
            handle.write(event("turn_aborted", "b", "2026-09-30T10:00:03Z"))
        watcher.poll()
        self.assertEqual(self.transitions, ["working", "idle"])


if __name__ == "__main__":
    unittest.main()
