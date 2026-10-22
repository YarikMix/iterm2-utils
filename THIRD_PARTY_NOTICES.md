# Third-party notices

`vendor/shell_integration/iterm2_shell_integration.zsh` is the unmodified official
iTerm2 zsh integration from gnachman/iTerm2, tag v3.7.6, Git blob
`efb57443f879239795411bcf076f38b4d1008b0f`.
Its original GPL-2.0-or-later license header is preserved verbatim. The accompanying
`vendor/shell_integration/LICENSE` is the verbatim upstream GPL version 2 text.
This vendored component remains under its own GPL license, separate from the
package's original MIT code. Source URLs, exact bytes' SHA-256 digests, tag and
blob identities are recorded in `sources.lock.json`; run
`python3 tools/check_sources.py` to verify the vendored bytes.

`vendor/codex_status/` adapts `YarikMix/iterm2-status` (MIT), public commit
`e749ff64a6b34252e9f41c5103f4b46831691443`. Its verbatim MIT license is retained in
`vendor/codex_status/LICENSE`. The transition implementation and locking/state
helpers derive from `scripts/status.py`; explicit-session command construction
replaces the external plugin discovery layer. Owned runtime settings and transport
live in `runtime/hook.py`; external plugin configuration/env is not required.
Canonical SHA-256 tool identities are computed transiently from input by
`runtime/events.py` and only the opaque identity persists, preserving upstream
parallel approval pairing where PermissionRequest lacks IDs and PostToolUse adds
an ID and omits its description. Raw commands, prompts, tool arguments and outputs
are never persisted. The 12 Lifecycle vectors in `tests/test_status_upstream.py`
are preserved unchanged; their import harness is adapted. Standalone installer,
external notification configuration and upstream process harness are not bundled.

These adapted modules are **not byte-identical** upstream copies. In
`sources.lock.json`, `upstream_sha256` identifies original downloaded content and
`sha256` identifies the final bundled bytes; `transformation` describes the patch.

`runtime/notifier.py` and `runtime/focus.py` adapt notification-state, foreground
lookup and exact-session focus patterns from the same MIT project. Their mapping
was reconciled against a newer installed local snapshot with no public SHA:
PermissionRequest banners had deliberately been removed because they precede
auto-review. `local_snapshot_sha256` records those inspected source bytes, while
`sha256` records this package's adapted module bytes; the public ref identifies
the available base, not the newer local snapshot. Claude hooks are a new adapter
based on the official Anthropic hooks and Python SDK schemas.
