# Notification events

Notifications are an explicit independent selection. They require Python 3.11+,
terminal-notifier and iTerm2 Automation access for the exact session lookup.
No live banners or macOS permission prompts have been verified by automated tests.

Codex custom notices cover request_user_input/request_user_input_async PreToolUse
and completion after a main Stop followed by idle. A Stop while subagents run
retains pending completion until upstream state reaches idle. PermissionRequest
never sends a custom banner: this hook precedes auto-review, so native TUI policy
alone decides whether approval is actually presented. The targeted
`tui.notifications = ["approval-requested"]` policy is verified for Codex 0.163.0;
unknown versions report unavailable and the current transaction engine blocks
installation. Previous bool/list values are retained by address-owned receipts.

Claude SessionStart resets state; UserPromptSubmit starts a new prompt, using
prompt_id or a counter advanced only by UserPromptSubmit. Notification with
permission_prompt, idle_prompt, elicitation_dialog or elicitation_url_dialog
requests attention, never a permission decision. Only main Stop completes a
prompt. Active background_tasks suppress completion until a later main Stop.
Duplicate Stop, stop_hook_active, SubagentStop, StopFailure, Interrupt and
SessionEnd do not produce completion. SessionEnd clears the active turn.
Source schema: https://code.claude.com/docs/en/hooks.md. Background-task
list semantics are confirmed by the official Python SDK StopHookInput and
BackgroundTaskSummary in https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/types.py:
all listed tasks are in flight, including unknown status strings. Any nonempty
malformed shape also suppresses completion conservatively, until a later main
Stop reports no background tasks. No task descriptions or commands persist.

A notice token is claimed under lock before delivery. Foreground originating
sessions, unknown/closed UUIDs and denied Automation access silently skip banners.
Click callbacks contain absolute quoted argv, select that UUID, then activate
only after successful selection. No fallback to the active tab exists.
The asynchronous terminal-notifier worker has a nine second subprocess timeout;
hook-side probes/helpers are bounded independently by the 2.7s overall hook alarm.
Caches retain state, bounded IDs, opaque upstream tool fingerprints, tokens and
timestamps, never prompts, raw tool inputs or assistant output.

The mapping follows the public pinned codex-status base e749ff64a6b34252e9f41c5103f4b46831691443 documented in
THIRD_PARTY_NOTICES.md and the newer locally installed notifications.py implementation. Its
local removal of PermissionRequest banners is intentional; a public SHA for that
newer local snapshot is unavailable. Artwork/title extraction is not transferred.

Attention deduplication is per request identity. Codex uses its opaque tool_key
and removes only the matching claim after PostToolUse. Different concurrent
questions each notify; retransmission of the same request is suppressed.
Claude's declared Notification schema has no request ID. Its opaque identity is
SHA-256(notification_type,title,message); raw fields never persist. Distinct
messages notify separately. PostToolUse and PostToolUseFailure reset only
attention claims, allowing a later same-text request to notify again without
resetting completion for the prompt. Identical parallel Claude requests with no
intervening resolution cannot be distinguished from retransmission and are
suppressed. The fingerprint is for transient attention identity, not content
storage. Schema evidence: official SDK NotificationHookInput at the URL above.
