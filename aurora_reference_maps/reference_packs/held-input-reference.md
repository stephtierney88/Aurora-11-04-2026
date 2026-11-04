# Held inputs and cancellation

Implementation 10 / roadmap 4B3, September 6, 2026. This contract covers Aurora's reviewed desktop/game dispatcher. Native application behavior still requires separate validation.

## Operating controls

| Command | Behavior |
| --- | --- |
| `SHOW_HELD_INPUTS()` | Read current owners, original backend/key/button, generation, release attempts and uncertainty. Also available as `work.held_inputs` in runtime state and `held_input_results` in the correlated receipt. |
| `RELEASE_HELD_INPUTS()` | Cancel active/queued command batches and release Aurora-owned inputs. Model work and Live remain unchanged. A new intentional command can run afterward. |
| `CANCEL_ACTIVE_WORK()` | Cancel model and command work and release owned inputs. Live remains unchanged; remote model work can continue draining. |
| `SHUTDOWN_RUNTIME()` | Request shutdown, cancel work and attempt owned releases. The shutdown receipt and final snapshot report incomplete cleanup. |
| `PYAG:hold(ctrl)` / `GB:hold(a)` | Retain indefinite holds. Omit duration or use `None`; no automatic timeout was added. The original request remains the owner until release/cancellation/shutdown. |
| `PYAG:release(ctrl)` / `GB:release(a)` | Prefer the hold's original route. GB release retains its press-time mapping/backend even after settings change, without acquiring focus again. A repeated released hold is a no-op. |
| `GB:release(a,current)` | Advanced recovery: explicitly send key-up through the currently selected mapping/backend. This bypasses the owned-route lookup and does not clear a different owned route. Untracked keys also retain the previous current-route key-up behavior. |

Use the namespace reported by `SHOW_HELD_INPUTS()` after changing action mode. Explicit `PYAG:` remains literal desktop input; `GB:` remains game input. An unprefixed command follows its admitted action mode.

## Ownership and failure

`aurora_input_ownership.HeldInputLedger` records a unique lease before native down, with the command generation, request/client/source identity when present, command name and original release callback. It retains scan-code/extended-key identity for SendInput, resolved scan codes for the keyboard backend, and physical mouse-button selection. Metadata does not copy raw typed text or command arguments into the owner record.

Timed holds, chords, game presses, drags and mouse holds release their own lease in cleanup. Partial down failures also attempt release. A failed release stays tracked as `release_uncertain`; other owned releases are still attempted. Inspect state and issue a **new** `RELEASE_HELD_INPUTS()` request to retry cleanup. Redelivering the same request ID returns the existing receipt without repeating native operations.

Cancellation closes the old generation. It cannot release a newer generation's hold, and stale lease cleanup cannot release a newer hold of the same key. If down/release is already in flight, stop reports `pending_operation`; the acquiring worker completes cleanup after it returns. `last_cleanup` is historical evidence, while `held` shows current outstanding records. No background cleanup watcher is created.

Unresolved cleanup blocks new desktop input, including unrelated keys and pointer movement: a possibly held modifier or mouse button could change its meaning. Inspection, screenshots and release/recovery remain available. Once cleanup is confirmed, new intentional input can proceed.

Aurora rejects a second conflicting hold/tap before native input so one command cannot release another command's held key. Release first, then issue the new action. This also protects owned Shift/Ctrl/Alt from PyAutoGUI's implicit character modifiers. A multi-hold setup that fails releases only leases it acquired. Ordinary typing/click behavior is retained; opaque atomic backend calls are tracked while running and get release cleanup if they raise.

## Timing and limits

Move/drag use immediate PyAutoGUI moves with cancellation checks and approximately 20 ms waits between interpolation steps. Drag owns its button for the movement and releases it on completion/cancellation/error. Long finite durations remain supported; waits are chunked to avoid operating-system timeout overflow. There is no promise that Windows can forcibly interrupt an individual native API call. A cancellation receipt is not proof that an application observed the release.

The ledger is process-local, capped at 256 simultaneous records and 256 recently released persistent routes. No held input is silently evicted. Repeated-release no-op memory is bounded and resets when a new hold uses that logical route. Graceful shutdown attempts cleanup; a process kill, crash, lost device or human physically holding the same key cannot be fully reconciled by these injection APIs. Cleanup sends key-up only for Aurora-owned records; it does not sweep every keyboard key.

## Verification and next work

See `docs/reviews/2026-09-06/implementation-10.md` and its validation/runtime-proof JSON. Tests use fake native APIs; native GUI/gameplay remains pending after the user's lag report. 4B4 critical mutation families comes next, followed by measured performance and GUI/clean-install acceptance.

Existing Chat Completions, models, auth, reasoning controls, game backends and command bindings remain available. Astra Responses `configuration_update` remains a separate opt-in Transport setting; see [adaptive reasoning](adaptive-reasoning-reference.md). Live provider/cache proof and explicit compaction remain follow-ups.
