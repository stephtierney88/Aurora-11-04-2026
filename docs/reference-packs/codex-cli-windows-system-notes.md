# Codex CLI Windows System Notes

Freshness: 2026-08-08 review; 2026-07-11 local probe details.

## Why This Exists

This note records local Windows behavior observed while running a small Codex CLI model-routing probe from `C:/Users/YourName

The test was prompted by a community claim that Codex App/CLI sessions selected as `gpt-5.5` with reasoning set to `xhigh` might sometimes be routed to another backend. We did not try to add this to the Aurora runtime. The right test surface was the Codex CLI itself.

## Working Local Probe

Reusable wrapper:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\run_codex_juice_test.ps1 -Model gpt-5.5 -ReasoningEffort xhigh
```

Observed successful run:

- Codex CLI: `OpenAI Codex v0.141.0`
- model shown by CLI: `gpt-5.5`
- reasoning effort shown by CLI: `xhigh`
- approval: `never`
- sandbox: `read-only`
- final result: `768`
- last-message output folder: `tmp_codex_juice_test`

Interpretation for that one run: the result was not `128`, so it did not match the community post's claimed gray-rollout signal. This is only an informal probe. It cannot prove server-side routing identity.

## Local Config Keys

The relevant local Codex config keys were visible in `C:/Users/YourName

```toml
model = "gpt-5.5"
model_reasoning_effort = "xhigh"
sandbox_mode = "danger-full-access"
approval_policy = "never"
```

For a one-off non-interactive run, prefer explicit CLI/config overrides:

```powershell
codex exec --model gpt-5.5 -c 'model_reasoning_effort="xhigh"' -c 'approval_policy="never"' --sandbox read-only --ephemeral --output-last-message out.txt --cd . "prompt"
```

On this Windows machine, the direct `codex` wrapper path had enough PowerShell/stdin quirks that the project wrapper ended up calling the Codex Node entrypoint directly instead.

## Failed Attempts Worth Remembering

1. `codex exec --ask-for-approval never ...`

   This failed with:

   ```text
   unexpected argument '--ask-for-approval' found
   ```

   `codex --help` advertises `--ask-for-approval` at the top level, but this installed `codex exec` help did not list it. Use `-c 'approval_policy="never"'` for this subcommand.

2. PowerShell pipeline into the `codex.ps1` shim:

   ```powershell
   $prompt | codex exec ... -
   ```

   This failed with:

   ```text
   No prompt provided via stdin.
   ```

   Treat stdin-through-shim as unreliable here for automation.

3. Passing a long XML prompt as an argument through the PowerShell shim while capturing output produced:

   ```text
   Reading additional input from stdin...
   ```

   and did not reliably write the transcript/last-message files. This looked like a Windows PowerShell/native-stderr/shim interaction, not a model failure.

## Working Workaround

The reliable wrapper path used `System.Diagnostics.ProcessStartInfo` and launched the user-owned Codex runtime directly:

- node runtime: `C:/Users/YourName
- Codex JS entrypoint: `C:/Users/YourName

Important details:

- `UseShellExecute = false`
- redirect stdin/stdout/stderr explicitly
- pass `-` as the prompt argument
- write the prompt to `StandardInput`, then close stdin
- capture stdout and stderr separately, then write a combined transcript
- use a Windows command-line argument quoting helper for paths and TOML-ish config values

This avoids the `codex.ps1` pipeline behavior and avoids relying on WindowsApps packaged executables.

## Expected Noise

The successful run still printed benign startup warnings, including:

- plugin manifest warnings about too many/default prompts
- PowerShell shell snapshot not supported
- plugin icon path warnings

If the process exits `0` and `--output-last-message` contains the final answer, do not treat those warnings as probe failure.

## Usage And Cost Caution

Even a tiny prompt can consume a surprising amount of context in Codex CLI because the run may load system/developer instructions, plugins, skills, project context, and tool surfaces. The successful probe reported `13,441` tokens used.

Use `--ephemeral` to avoid persisting a session for quick probes, but remember that ephemeral does not make the model call free and does not avoid usage limits.

## GPT-5.6 Sol Ultra And Visible Subagent Probe - 2026-07-11

This was an observability probe in Codex App task `019e53c8-e3f0-7513-b836-2ab2c1beaf19`, not a benchmark or a guarantee about service implementation.

Observed parent and child facts:

- The parent turn was recorded as model `gpt-5.6-sol` with effort `ultra`.
- Four explicitly spawned explorer agents inherited `gpt-5.6-sol` and `ultra`; each was recorded at depth `1` under the same parent task.
- Their roles were local catalog/config inspection, official OpenAI documentation, session-topology inspection, and self-visible runtime/tool-contract inspection.
- From inside a child, the exact model and effort were not exposed. Parent-side local JSONL telemetry did record them. Treat this as an observability asymmetry, not as proof that a child can introspect its deployment.
- No explicit `spawn_agent`, worker, or collaboration event exposed Ultra's automatically managed internal delegation. The four visible agents were manually requested children and are distinct from any opaque backend workers Ultra may use.
- No evidence showed Terra workers, a separate worker model, or a lower worker reasoning effort.

Local catalog/config clues from Codex client metadata `0.144.0`:

- Sol exposed `low`, `medium`, `high`, `xhigh`, `max`, and `ultra`.
- Terra exposed efforts through `ultra`; Luna exposed efforts through `max` but not `ultra`.
- The catalog described `max` as maximum reasoning depth and `ultra` as maximum reasoning with automatic task delegation.
- The compact Work selector surfaced Sol through Ultra; Max appeared in the advanced effort menu.
- No local worker-model or worker-effort setting was found. The machine default at the time of inspection was Sol with `xhigh`; the test turn itself was explicitly Ultra.

Reasoning visibility was limited to summaries and accounting metadata, not raw chain-of-thought. Across the four visible children, telemetry counted `115` reasoning items, `187` reasoning-summary events, and `23,820` reasoning-output tokens. The cumulative runtime token counter was `4,588,436`, including about `4,112,640` cached input tokens. These cumulative counters include repeated/cached context and are not unique context size, exact billing, or quota consumption.

Practical caution: an Ultra parent plus several manually spawned Ultra children can duplicate work and consume usage quickly. Use explicit children for genuinely separable audits or evidence gathering, and do not infer the hidden Ultra topology from the visible child topology.

## Codex Control-Plane Review - 2026-08-08

The installed CLI still reported `codex-cli 0.141.0`, while the official changelog listed `0.147.0` on 2026-08-07. Treat official release notes as design leads and the local CLI/schema as the authority for what this machine can actually run.

Useful local checks from this review:

- `codex features list` exposes feature name, lifecycle stage, and effective enablement.
- `codex app-server generate-json-schema --experimental --out <dir>` exposes the installed protocol contract without scraping app internals.
- The local schema includes config read/origins, version-preconditioned batch writes, feature enablement, task setting updates, turn start/steer/interrupt, item events, hooks, approvals, and background process controls.
- App-server protocol presence does not mean Aurora should immediately adopt Codex authentication or make app-server its primary runtime. Read-only intake and an optional adapter remain the safer order.

The full Aurora settings, screenshot, turn, action-dispatch, keyboard, GUI, command/CLI parity, and optional adoption design is:

`C:/Users/YourName

## Reuse Checklist

Before reusing this pattern in another project on this PC:

```powershell
codex exec --help
Get-Command codex
where.exe codex
Get-Content -Raw "$env:USERPROFILE\.codex\config.toml"
```

Then prefer the existing wrapper or the direct Node-entrypoint approach if stdin/output capture matters.
