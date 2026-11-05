# Aurora 2 Control Panel — lite map

Public snapshot: November 5, 2026, release 54. The Control Panel remains a client of the shared runtime/control plane; local drafts do not become effective state until an acknowledged apply. There are 24 views, with full access through the View selector/Advanced controls.

| Surface | Main source and behavior |
| --- | --- |
| Main shell/header | aurora2_control_panel.py; Conversation-first startup, compact/expanded header, Panel options and persistent runtime controls |
| Agent controls | aurora_agent_controls.py; auth/model/effort, one-turn overrides, execution/flow and bounded-task controls |
| Sign-in | aurora_chatgpt_panel.py; explicit login/registration, account selection and token-free status; does not enable inference or select billing |
| Conversation | aurora_conversation.py, aurora_conversation_delivery.py; current/retained/history views and session outbox/delivery stages |
| Mini-preview/editor | aurora_conversation_navigator.py; readable or legacy compact view, docking/popout/jump and revision-checked edit/pin |
| Switchboard | aurora_switchboard.py; flow/context inspection, model drafts, switches, command prepare/submit and receipts |
| Shared layout | aurora_panel_layout.py; work-area fitting, width-aware labels, scroll containers and settled repaint |
| Settings/recovery | shared registry/transactions and default profiles; Preview/Apply/Undo, scoped reset, effective receipts |
| Dashboard | shared sanitized dashboard snapshots; stable rows/selection and expanded receipt inspector |

Conversation is the eligible chat portion, not the entire exact inference payload. Context chips expose bounded prepared components; flow arrows describe observed configuration, not full causal telemetry. Current model, requested model and provider-reported model are separate evidence.

Mini-preview defaults to readable excerpts. Dock/collapse/popout and View options retain the compact colored map, metadata and transcript formats. Model context windows are estimates. Archived/deleted views do not prove inclusion in a request. Decay remains append-triggered, with separate pinned/image controls.

Outbox/Awaiting reply retain submitted text and initial delivery stages in the panel session. Restart recovery, queued cancellation and safe manual retry remain CP1c. Message editing keeps sender and editor separate and fails on stale revision rather than overwriting silently.

Switchboard marks unapplied drafts amber. Preview and Apply use versioned settings; model selectors apply their own subset. Raw-command yellow prepares and green submits. A submission receipt is not proof of physical success. Reset lists its reviewed controls without wiping credentials/files/history; it is a scoped baseline, not every Advanced setting.

Optional task outcomes/budgets and carry policies use the shared settings authority. Advisory hierarchy, preserved explicit horizons and bounded subscription policy are searchable Advanced controls; they retain legacy defaults. The subscription choice is session-only/next-request. SHOW_TASK_STATUS and Raw State expose bounded correlated progress, missing evidence and unverified declared outcomes. Task-held proposals still require deliberate operator handling.

Release 54 restores the missing subscription-policy field in the full state export. Its absence had blocked unrelated GUI settings transactions too; effective-state checks and subscription Preview/Apply/Undo are now exercised in the guarded panel fixture.

Remaining polish: less vertical stacking, reachable Apply/Undo/results on small displays, keyboard/focus coverage, very short preview legends, mixed-DPI and live-load rendering. Existing synthetic refresh checks are useful but do not certify every Windows driver/monitor combination.

See [human guide](../../README_FOR_HUMANS.md), [release notes](../../RELEASE_NOTES.md), [roadmap](../../docs/notes/aurora_runtime_roadmap.md) and adjacent generated UI skeleton/call-tree/index.
