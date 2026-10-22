# Upstream Lifecycle vectors unchanged; only module-loading harness adapted.
import json
import unittest
from vendor.codex_status import status
UUID = "11111111-2222-3333-4444-555555555555"
UUID2 = "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE"


def event(name, **extra):
    return dict({"session_id": "root-session", "cwd": "/private/test-project", "hook_event_name": name}, **extra)


class Lifecycle(unittest.TestCase):
    def test_lifecycle_and_approval(self):
        state = status.transition({}, event("SessionStart"))
        self.assertEqual(state["status"], "idle")
        state = status.transition(state, event("UserPromptSubmit"))
        tool = dict(tool_name="Bash", tool_input={"command": "printf test"})
        state = status.transition(state, event("PreToolUse", **tool))
        state = status.transition(state, event("PermissionRequest", **tool))
        self.assertEqual(state["status"], "waiting")
        state = status.transition(state, event("PostToolUse", **tool))
        self.assertEqual(state["status"], "working")
        state = status.transition(state, event("Stop"))
        self.assertEqual(state["status"], "idle")
        state = status.transition(state, event("SessionEnd"))
        self.assertEqual(state["status"], "")
        self.assertIsNone(status.transition(state, event("PostToolUse", **tool)))

    def test_waiting_survives_unrelated_parallel_tool(self):
        state = status.transition({}, event("UserPromptSubmit"))
        blocked = dict(tool_name="Bash", tool_input={"command": "one"})
        other = dict(tool_name="Bash", tool_input={"command": "two"})
        state = status.transition(state, event("PermissionRequest", **blocked))
        for hook in ["PreToolUse", "PostToolUse"]:
            state = status.transition(state, event(hook, **other))
        self.assertEqual(state["status"], "waiting")
        state = status.transition(state, event("PostToolUse", **blocked))
        self.assertEqual(state["status"], "working")

    def test_real_codex_permission_description_is_not_part_of_identity(self):
        state = status.transition({}, event("UserPromptSubmit"))
        state = status.transition(state, event("PermissionRequest", tool_name="Bash",
            tool_input={"command": "printf CODEX_PERMISSION_TEST", "description": "Verify status"}))
        self.assertEqual(state["status"], "waiting")
        state = status.transition(state, event("PostToolUse", tool_name="Bash",
            tool_use_id="exec-123", tool_input={"command": "printf CODEX_PERMISSION_TEST"}))
        self.assertEqual(state["status"], "working")
        self.assertEqual(state["waiting"], {})

    def test_input_tool_and_interrupt(self):
        tool = dict(tool_name="request_user_input", tool_input={"questions": ["private question"]})
        state = status.transition({}, event("PreToolUse", **tool))
        self.assertEqual(state["status"], "waiting")
        self.assertNotIn("private question", json.dumps(state))
        state = status.transition(state, event("Interrupt"))
        self.assertEqual(state["status"], "idle")

    def test_background_agents_survive_parent_stop(self):
        state = status.transition({}, event("UserPromptSubmit"))
        for agent in ["a", "b"]:
            state = status.transition(state, event("SubagentStart", agent_id=agent))
        state = status.transition(state, event("Stop"))
        self.assertEqual(state["status"], "working")
        state = status.transition(state, event("SubagentStop", agent_id="a"))
        self.assertEqual(state["status"], "working")
        state = status.transition(state, event("SubagentStop", agent_id="b"))
        self.assertEqual(state["status"], "idle")

    def test_old_session_cannot_clear_replacement(self):
        state = status.transition({}, event("UserPromptSubmit"))
        replacement = dict(event("SessionStart"), session_id="new-session")
        state = status.transition(state, replacement)
        self.assertIsNone(status.transition(state, event("SessionEnd")))

    def test_compaction_keeps_session_working(self):
        state = status.transition({}, event("SessionStart", source="compact"))
        self.assertEqual(state["status"], "working")

    def test_terminal_id_is_explicit_uuid(self):
        self.assertEqual(status.terminal_id("w0t2p0:" + UUID), UUID)
        for invalid in ["", "active", "all", "$(touch bad)", UUID + ";x"]:
            self.assertIsNone(status.terminal_id(invalid))

    def test_identical_parallel_approvals_wait_for_both_completions(self):
        state = status.transition({}, event("UserPromptSubmit"))
        tool = dict(tool_name="Bash", tool_input={"command": "same command"})
        for _ in range(2):
            state = status.transition(state, event("PermissionRequest", **tool))
        state = status.transition(state, event("PostToolUse", **tool))
        self.assertEqual(state["status"], "waiting")
        state = status.transition(state, event("PostToolUse", **tool))
        self.assertEqual(state["status"], "working")

    def test_resume_clears_old_waiting_and_background_state(self):
        state = status.transition({}, event("PermissionRequest", tool_name="Bash"))
        state = status.transition(state, event("SubagentStart", agent_id="old"))
        state = status.transition(state, event("SessionStart", source="resume"))
        self.assertEqual(state["status"], "idle")
        self.assertEqual(state["agents"], [])

    def test_late_stop_cannot_clear_a_new_turn(self):
        state = status.transition({}, event("UserPromptSubmit", turn_id="one"))
        state = status.transition(state, event("UserPromptSubmit", turn_id="two"))
        self.assertIsNone(status.transition(state, event("Stop", turn_id="one")))
        self.assertEqual(status.transition(state, event("Stop", turn_id="two"))["status"], "idle")

    def test_control_characters_do_not_reach_status_detail(self):
        state = status.transition({}, event("UserPromptSubmit", cwd="/tmp/project\x1b\x00\u202e"))
        self.assertEqual(state["detail"], "Codex · project")

