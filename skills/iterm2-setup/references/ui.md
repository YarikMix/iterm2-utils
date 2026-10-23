# Pending UI and verification

Read the CLI `ui` entries and preserve their codes; UI completion is not inferred
from a successful install, an installed Peekaboo binary or the user's “done”.
Use a connected, permitted Peekaboo tool if present in this agent session. If it
is absent, disconnected or denied, provide the manual steps below and keep the
feature pending. Never install Peekaboo silently, grant permissions, change TCC
or try a second UI method after a policy denial.

- Python API: iTerm2 → Settings… (Настройки…) → General (Основные) → Magic →
  Enable Python API (Включить Python API). The label may remain English in a
  localized build. The colleague handles the authorization dialog for the pinned
  MCP server. Afterwards run the pending `mcp_authorize` or `python_api` code with
  `python3 -m iterm2_utils reconcile --step CODE --json` and a live doctor probe.
  A failed connection leaves pending state; do not claim ready.
- Profile for a **new tab**: top-level Profiles (Профили) → selected profile opens
  a new tab. Applying to the **existing tab**: Session (Сеанс) → Edit Session…
  (Изменить сеанс…) → choose the profile → Use Selected Settings (Использовать
  выбранные настройки). Verify automatic switching is not prevented for that
  session. Do not switch or restart someone else's tab automatically.
- Claude native status: iTerm2 application menu → Install/Reinstall Claude Code
  Integration (Установить/переустановить интеграцию Claude Code). Choose only API,
  hooks and Session Status (Статус сеанса); leave Workgroup and Auto-Enter
  unchecked. Read the CLI instruction for `claude-native-status`; the colleague
  confirms installation and hook trust. Run `reconcile --step claude-native-status
  --json` to verify recognized cc-status hooks, preserving existing foreign hooks.
  If the control is unavailable, report that capability rather than installing a
  competing hook.

A new session may be required to load hooks or an MCP registration. Tell the
colleague; never restart it automatically. System permission dialogs always
remain human actions, including when Peekaboo can navigate normal app settings.

Codex native status has no ready official installer menu: use the existing
selected package plan/install (or update for owned beta.1 hooks). Do not apply
Claude's menu checkpoint to Codex. New hooks still require human trust and may
need a fresh session. Leave independent notifications/restore unselected unless
requested. A successful save or API read does not verify event delivery; Codex
0.163.0 cannot supply StopFailure for automatic API-error status.
