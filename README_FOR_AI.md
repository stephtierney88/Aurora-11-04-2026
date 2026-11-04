# Aurora: guide for AI operators and coding assistants

Read [the human setup guide](README_FOR_HUMANS.md), `AGENTS.md`, `docs/notes/aurora_current_status.md`, `docs/notes/aurora_runtime_roadmap.md` and `docs/notes/aurora_capability_compatibility.md`. Public snapshots have curated status/roadmap notes; do not infer that omitted private development history is missing implementation. Read source and generated maps for implementation claims.

## Orientation

- `aurora2.py`: runtime, inference, prompt assembly, memory, scheduler, command dispatch and native actions.
- `aurora2_control_panel.py`: separate Tk process reading exported state and writing the external inbox. It does not own a second inference engine.
- `aurora_control_plane.py`, `aurora_command_protocol.py`, `aurora_command_contracts.py`: shared ingress, admission, identity and receipt boundaries.
- `aurora_settings_registry.py`, `aurora_settings_transactions.py`, `aurora_default_profiles.py`: typed settings, transactions, profiles and rollback.
- `aurora_conversation.py`: bounded detached current/retained conversation exports. Historical JSONL logs are a separate surface.
- `aurora_episodic_retrieval.py`, `aurora_search_query.py`, `aurora_retrieval_commands.py`, `aurora_retrieval_results.py`: ranking, filters, query admission, receipts and bounded retained result handles.
- `aurora_validation_console.py` / `aurora_validation_web`: local source-aware command browser and offline validation console. No hosted desktop bridge or live-provider qualification is implied.
- `aurora_reference_maps/runtime/overview.md`, UI lite/deep maps and function skeletons: start here before scanning the monolith. Regenerate references after source changes using `python tools/generate_aurora_references.py` and verify with `--check`.

## What the runtime model receives

The model does not automatically read these Markdown files or all source files. Each ordinary inference builds a base system prompt via `build_base_system_prompt()`, then working-memory state, eligible optional episodic/context material, selected recent history, and the current message/image. Runtime details and prompt ledgers expose parts of this process. The Conversation page is only the eligible conversation portion, not the entire API request.

Default startup uses `INIT_MODE='test'` and `LOAD_LIVE_INIT_PROMPT=False`. Despite the historical name, `test_init_prompt` is the short current assistant profile. It is retained as Init history at initialization and included as persistent init context in the base prompt. `--live-init` or `--init-mode load` loads `aurora2_init.txt`; `--init-mode skip` skips the optional init, while the base system prompt still exists. Live Init in Advanced settings applies at the next initialization; it does not hot-reload an already-loaded file.

The November 4 extended profile is about 5.9k characters, below the default 12k persistent-init cap. The prior file was about 14.4k characters and last committed March 8; its persistent-system portion could be clipped, while the Init history path could separately retain more. Do not claim the old prompt was wholly absent or wholly visible without inspecting the actual packed request. Duplicate Init inclusion is a known optimization follow-up.

Prompt compatibility options are startup environment configuration:

| Setting | Meaning |
| --- | --- |
| `AURORA_INIT_PROMPT_PROFILE=current` | Updated short prompt, current extended filename, current command guidance; default |
| `AURORA_INIT_PROMPT_PROFILE=legacy` | Original short prompt and preserved `aurora2_init_legacy.txt`; original base guidance remains |
| `AURORA_LIVE_INIT_FILENAME` | Explicit extended init filename/path override |
| `AURORA_COMMAND_DISCOVERY_CONTEXT=on` | Add model-requested catalog results to conversation context; current default |
| `AURORA_COMMAND_DISCOVERY_CONTEXT=off` | Preserve terminal-only catalog output; legacy default |
| `AURORA_MAX_INIT_PROMPT_CHARS` | Persistent-init character cap, minimum 2000, default 12000 |

Current prompt guidance distinguishes proposals/receipts/outcomes, data from operator instructions, screenshot freshness/coordinates, permission from capability, and one-turn effort changes from current inference. Prompts are guidance, not a security boundary or proof of model obedience. Runtime policy must enforce restrictions.

## Discover and use commands

The complete arsenal is not injected into every prompt. Discover it through generated catalogs, CLI or runtime commands. Runtime examples intended for execution:

```text
Executed Commands:
SEARCH_COMMANDS(screenshot, medium)
LOOKUP_COMMAND(REQUEST_SCREENSHOT_CAPTURE, high)
```

Use one command per line without fences when actually sending this format to Aurora. Do not put hypothetical examples in an executable section. Existing aliases and formats remain; inspect the parser before changing them. `LIST_COMMANDS(low)` is bounded; narrow search/lookup is often more useful. Model-requested lookup output is now added to context when enabled, including lookup errors. Operator terminal lookups retain terminal-only behavior.

Examples to inspect before use: `SHOW_RUNTIME()`, `SHOW_PENDING_COMMANDS()`, `UPDATE_CONTEXT(...)`, `RECALL(...)`, `REQUEST_SCREENSHOT_CAPTURE(reason, 0)`, and `SET_NEXT_INFERENCE(model=gpt-6-astra; reasoning_effort=medium; note=Review ambiguity)`. Do not self-approve held commands or bypass locks. Use stable IDs/version evidence where supported; distinguish queued, submitted, executed, uncertain and visibly verified states.

New model defaults: `gpt-6.1-sol` low text/vision and `gpt-6-astra` medium review role. Both use low/medium/high/xhigh/max, not none/minimal. Explicit profiles/settings can override this. Chat Completions uses Aurora's text command parser; do not mistake this for native API function calling. Responses configuration updates remain an optional separate transport path. A requested next-turn override is not a mid-inference change; verify application and restoration.

## Validation and privacy

Start with `aurora_preflight.py --json`, `python -m unittest discover -s tests -p "test_*.py"`, and `python tests/offline_runtime_smoke.py --contracts-only`. Native GUI fixtures need an interactive desktop; live-provider fixtures require explicit operator scope and bounded spending. Inspect each test's guards and copied-file list. No test name alone guarantees zero input/capture/API use.

Preserve all commands, aliases, profiles, toggles and valid legacy behavior. Compact GUI work must not reduce capability. Use one shared admission/settings/receipt authority. Do not import the full runtime merely for static discovery when AST/catalog helpers suffice: it has startup dependencies and side effects.

Never commit keys, OAuth caches, `.env` files, runtime history/state, personal defaults, screenshots or private Git history. Reuse configured keys without printing them. Track owned processes, windows, ports and temporary paths; clean only your resources. Preserve unrelated Portal/Browser/APP/OBS/SSH work.

Known limits: single-host native evidence; sparse Tk accessibility; session-local outgoing messages; production screenshot-coordinate/background-capture acceptance pending; catalog output is bounded; some historical prompt duplication; retrieval publication/concurrency work still pending. Timestamp filtering is not exact historical state reconstruction. Advanced versioned memory and fuller goal horizons remain staged options, not implemented guarantees.
