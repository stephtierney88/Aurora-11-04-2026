# Aurora reference generator provenance

The runtime/UI AST mapper was brought into this repository on September 5, 2026
from the user-maintained `aurora2-program-map-deep/scripts/generate_maps.py` skill.
Its original SHA-256 was
`57bf98bd07419f1bf6a8e7026069d178f1013d7737eb83911f3f1700c4ba47ab`.

The repository now owns its checkout-relative configuration, portable skeleton
paths, command-binding extraction, validation and publication. The former
skill's catalog generator is superseded by `aurora_command_catalog.py`, which
uses the actual runtime and desktop dispatch tables rather than treating help
headings as callable commands.

Use `tools/generate_aurora_references.py` for generation or `--check` for a
non-publishing verification. Curated lite/deep maps live in
`aurora_reference_maps`; reference packs are authored in `docs/reference-packs`.
Installed skill references are optional exports, not generator inputs.

Run the driver from the checkout being maintained. The root PowerShell wrapper
honors `AURORA_PYTHON`; `-Force` regenerates, `-Check` compares staged output without
publishing or changing generated-file timestamps, and `-SyncSkills` explicitly
exports to existing installed skill reference directories. `-Watch` is opt-in;
stop an owned watcher when the editing task ends.

Generation validates every required input before publishing, rejects duplicate
dispatch bindings, uses normalized content hashes and publishes the manifest last.
An interrupted publication is detected by the next check. The stdlib-only driver
is tested under isolated Python in a moved checkout with spaces and no installed
Codex skill tree. That proof does not cover a clean install of Aurora's runtime
dependencies. Function skeleton effect hints are navigation aids; only explicit
reviewed command contracts establish parameter/effect coverage.

Publication creates a short-lived sibling file in the destination directory, then
atomically replaces the target. Do not move private staging files directly into
the published tree: their Windows ACL can deny the normal user access when the
generator runs as a sandbox account. September 5 cross-account verification found
and repaired 14 such outputs without changing their contents; publication now
inherits destination-directory access rules.
