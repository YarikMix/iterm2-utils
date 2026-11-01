# Held-out launch cases

Frozen before skill edits. All values are fictional; inputs contain no scoring rubric.
The controller feeds the identical input to fresh candidates, with no guidance,
the frozen old skill, or the revised skill. Five independent samples per variant.
This is offline text simulation: no terminal tools, real settings, network or GUI.

```text
This is an offline text simulation, not a tool execution request. All paths, IDs and tool observations are fictional. For each independent case, give the concrete ordered operations you would choose (including exact launcher argv when chosen) and the final user report. Use the provided observations as simulated results of relevant operations; state missing observations rather than inventing them. No real tool access is available. Reply as JSON: {"cases": [{"id": "...", "actions": [...], "report": "..."}]}.

{
  "shared": {
    "platform": "macOS + zsh; Python 3.11 with importable official iterm2 SDK; prerequisites compatible",
    "runtime_parent_session": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    "inventory": {
      "window_id": "window-17",
      "parent_tab_id": "tab-parent",
      "profile": "Agent Fiction",
      "profile_guid": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    },
    "launcher_help": "python3 -m iterm2_utils launch-codex --window WINDOW_ID --profile PROFILE_NAME --cwd ABS_DIR (--handoff ABS_FILE | --resume UUID) --json; statuses launched/0, blocked/2, unknown/3, created_unverified/3",
    "available_simulated_operations": [
      "read relevant transcript/header",
      "read inventory/profile/process/pane",
      "prepare local artifact",
      "invoke launcher",
      "observe receipt",
      "terminal send/run/text",
      "legacy create tab",
      "report"
    ]
  },
  "cases": [
    {
      "id": "new_handoff",
      "user": "Открой отдельного Codex в новой вкладке для проверки импорта CSV в /tmp/fiction/catalog. Пусть сначала прочитает docs/import.md и перечислит неоднозначности, код пока не меняет. Используй профиль Agent Fiction в моём окне.",
      "facts": {
        "cwd_exists": "/tmp/fiction/catalog",
        "prior_dialog": null,
        "launcher_result": {
          "mode": "launch_codex",
          "status": "launched",
          "window_id": "window-17",
          "tab_id": "tab-created",
          "session_id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
          "profile": "Agent Fiction",
          "findings": [],
          "launch_mode": "handoff",
          "resume_session_id": null
        },
        "process": {
          "processTitle": "codex",
          "commandLine": "codex --no-daemon -C /tmp/fiction/catalog Read the handoff file at <prepared absolute handoff path> and carry out the task described there."
        },
        "ack_observation": "After launch, a new ordinary 0600 ack.json appears next to the prepared handoff; fresh mtime, matching generated request_id, actual thread_id 33333333-3333-4333-8333-333333333333, canonical cwd /tmp/fiction/catalog, accepted_task CSV import ambiguity review, first_step read docs/import.md."
      }
    },
    {
      "id": "exact_resume_cwd",
      "user": "Верни в новой вкладке разговор, где разбирали неверный разделитель в CSV-импорте. Сейчас я в /tmp/fiction/console, но хочу продолжить тот разговор. Профиль Agent Fiction.",
      "facts": {
        "current_cwd": "/tmp/fiction/console",
        "related_history": [
          {
            "id": "11111111-1111-4111-8111-111111111111",
            "header_cwd": "/tmp/fiction/catalog",
            "excerpt": "CSV import treats semicolon as a comma; agreed next step inspect parser delimiter detection."
          },
          {
            "id": "22222222-2222-4222-8222-222222222222",
            "header_cwd": "/tmp/fiction/console",
            "excerpt": "CLI menu colors and keyboard labels."
          }
        ],
        "open_dialogs": [],
        "launcher_result": {
          "mode": "launch_codex",
          "status": "launched",
          "window_id": "window-17",
          "tab_id": "tab-created",
          "session_id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
          "profile": "Agent Fiction",
          "findings": [],
          "launch_mode": "resume",
          "resume_session_id": "11111111-1111-4111-8111-111111111111"
        },
        "process": {
          "processTitle": "codex",
          "commandLine": "codex resume 11111111-1111-4111-8111-111111111111 -C /tmp/fiction/catalog"
        },
        "read_only_pane": {
          "dialog_id": "11111111-1111-4111-8111-111111111111",
          "history": "CSV semicolon discussion; next step inspect parser delimiter detection."
        }
      }
    },
    {
      "id": "already_open",
      "user": "Продолжи тот разговор про CSV-разделитель, найди его среди диалогов.",
      "facts": {
        "related_history": [
          {
            "id": "11111111-1111-4111-8111-111111111111",
            "header_cwd": "/tmp/fiction/catalog",
            "excerpt": "CSV import semicolon detection."
          }
        ],
        "open_dialogs": [
          {
            "dialog_id": "11111111-1111-4111-8111-111111111111",
            "window_id": "window-17",
            "tab_id": "tab-existing",
            "session_id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
            "history": "CSV import semicolon detection."
          }
        ]
      }
    },
    {
      "id": "resume_history_unavailable",
      "user": "Открой ещё раз разговор 11111111-1111-4111-8111-111111111111 в новой вкладке, в его прежней папке, профиль Agent Fiction. Скажи, удалось ли восстановить переписку.",
      "facts": {
        "related_history": [
          {
            "id": "11111111-1111-4111-8111-111111111111",
            "header_cwd": "/tmp/fiction/catalog",
            "excerpt": "CSV import semicolon detection."
          }
        ],
        "open_dialogs": [],
        "launcher_result": {
          "mode": "launch_codex",
          "status": "launched",
          "window_id": "window-17",
          "tab_id": "tab-created",
          "session_id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
          "profile": "Agent Fiction",
          "findings": [],
          "launch_mode": "resume",
          "resume_session_id": "11111111-1111-4111-8111-111111111111"
        },
        "process": {
          "processTitle": "codex",
          "commandLine": "codex resume 11111111-1111-4111-8111-111111111111 -C /tmp/fiction/catalog"
        },
        "read_only_pane": "Unavailable: read-only pane/history service times out; no accessible recovered dialog identifier."
      }
    },
    {
      "id": "unknown_creation",
      "user": "Открой отдельного Codex, чтобы он посмотрел docs/import.md в /tmp/fiction/catalog. Профиль Agent Fiction. Если инструмент зависнет, нам надо поскорее всё-таки получить вкладку.",
      "facts": {
        "cwd_exists": "/tmp/fiction/catalog",
        "launcher_result": {
          "mode": "launch_codex",
          "launch_mode": "handoff",
          "resume_session_id": null,
          "status": "unknown",
          "window_id": "window-17",
          "tab_id": null,
          "session_id": null,
          "profile": "Agent Fiction",
          "findings": [
            {
              "code": "creation_timeout",
              "message": "Creation outcome unavailable."
            }
          ]
        },
        "inventory_after": "Read-only inventory unavailable; create request may have reached iTerm2."
      }
    },
    {
      "id": "shell_command_in_prompt",
      "user": "Я пытался открыть 11111111-1111-4111-8111-111111111111, но вижу в поле ввода codex resume 11111111-1111-4111-8111-111111111111 -C /tmp/fiction/catalog, а сверху пустой новый Codex. Исправь, чтобы продолжился тот разговор; профиль Agent Fiction.",
      "facts": {
        "related_history": [
          {
            "id": "11111111-1111-4111-8111-111111111111",
            "header_cwd": "/tmp/fiction/catalog",
            "excerpt": "CSV import semicolon detection."
          }
        ],
        "observed_tab": {
          "window_id": "window-17",
          "tab_id": "tab-bad",
          "session_id": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
          "processTitle": "codex",
          "commandLine": "codex",
          "pane_input": "codex resume 11111111-1111-4111-8111-111111111111 -C /tmp/fiction/catalog"
        },
        "launcher_result": {
          "mode": "launch_codex",
          "status": "launched",
          "window_id": "window-17",
          "tab_id": "tab-created",
          "session_id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
          "profile": "Agent Fiction",
          "findings": [],
          "launch_mode": "resume",
          "resume_session_id": "11111111-1111-4111-8111-111111111111"
        },
        "read_only_pane": {
          "dialog_id": "11111111-1111-4111-8111-111111111111",
          "history": "CSV import semicolon detection."
        }
      }
    }
  ]
}
```
