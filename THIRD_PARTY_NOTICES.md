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

`runtime/codex_restore/` and `tests/restore/` bundle only the codex-resume
module from agent-utils, subtree commit
`15f225cb4ac15abb7f95f87cbddc7406ba0ba7f9`, author y.mihalev.
The standalone installer and its test are excluded; common feature builders
replace installation. The legacy source subtree had no separate license declaration. The bundled port
is distributed by its author under this repository's MIT license; this does not
assert a license for the legacy repository. Source provenance is preserved.
The source runtime contracts, lifecycle timeouts and behavioral vectors are
preserved. Test imports/entry paths are relocated; iTerm process identification
accepts the selected installed app path. An uncertain tab-create result now
retains its reservation and asks for inspection, preventing automatic retries.
Tab creation also accepts an explicit profile and command as separate arguments,
validates them before creation, and preserves the returned tab identity when later
session inspection fails. Legacy restore calls retain their original arguments.
The local metadata bridge forwards only session_id, cwd, transcript_path and
hook_event_name transiently; it never persists hook content. Per-file original
and bundled SHA-256 digests are recorded in sources.lock.json.

The package restore shell adapter now invokes its entrypoint with the selected,
validated runtime Python; standalone source usage retains its original fallback.
`runtime/codex.zsh` also adapts the author's pinned restore argument classifier so
service commands after global options work without selecting restore. The source
ref/original hash and bundled hashes remain separate in sources.lock.json. Local
port entries explicitly link this repository's LICENSE and these notices; they
do not assign a license to the legacy repository.

`runtime/assets/appearance/` contains nine named SVG/PNG pairs. The generic
phone (`ios`), robot (`android`) and cutlet (`kotlett`) are original illustrations
created for this repository and distributed under its MIT license (LICENSE).
The six service/platform composites reuse the phone or robot, or the official
Chrome logo, with branded Mail or Cloud artwork from these public sources:

| Artwork | Public upstream SVG | Upstream SHA256 |
| --- | --- | --- |
| Mail `@` | https://cloud.imgsmail.ru/cloud.mail.ru/hashes/img/portal-header/38ee4afd7a08350c7d70.svg | `8797246440d02769af6ae58cf3fdd90f9ce56858f02098a0dee5a8b659129897` |
| Cloud | https://cloud.imgsmail.ru/cloud.mail.ru/hashes/img/54cbc3d30f0b1da1d208.svg | `71706ae50083d481d84e172308b858abba2979b2f90dff08d6d2ee0da0ffb333` |
| Google Chrome | https://www.google.com/chrome/static/images/chrome-logo-m100.svg | `1357dd965397a99cbc937ddd2345a9897d527f7229c8b0f2aeebac97680cc66d` |

Mail and Cloud artwork and marks belong to Mail / VK; Chrome artwork and marks
belong to Google. These upstream graphics are third-party brand artwork, not
original package drawings, and are not covered by this repository's MIT grant.
No separate license grant for that artwork is asserted here.

Transformations: only the separate `@` path from the Mail 135×30 wordmark is
used (the 0..30 area, without wordmark text), recolored white and placed on a
rounded `#0077FF` square. Cloud's rounded blue square and white contour, and
Chrome's colored paths and gradients, are scaled proportionally. Each composite
places the larger platform behind a 74×74 service badge at the bottom right
of the transparent 128×128 canvas; all paths and gradients are inline in SVG.
PNG files were rendered from the accompanying SVG with librsvg `rsvg-convert`;
the renderer is a developer tool and is not bundled or required for installation
or shell startup. No internal-repository artwork is included.

All nine named PNG/SVG pairs and these notices ship in immutable installed
runtime releases and the public archive; installation and shell startup do not
download images. The shared `runtime/codex.zsh` adaptation also adds optional
appearance launch/return phases without changing its pinned source identity or
the original restore classifier attribution above.
