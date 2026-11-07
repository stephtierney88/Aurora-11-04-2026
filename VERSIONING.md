# Aurora release identity

Current release: **Aurora 2 · Preview 84 · November 6, 2026**.
Immutable annotated Git tag: **`preview-2026.11.06-r84`**.

Release dates use America/Los_Angeles; the build also records UTC time. The family is `aurora2`, the channel is `preview`, and the serial is a monotonically increasing implementation/release identifier. Branches use `codex/<purpose>`; Git ancestry records lineage without embedding branch ancestry in long names. A preview serial is not a claim of semantic-version compatibility or production readiness.

`aurora_control_plane.release_info()` supplies the Control Panel title and runtime export identity. Public `SNAPSHOT.json` records the same identity, source revision and SHA-256 of every exported file except the manifest itself. The release commit supplies the immutable Git identity; inserting its own hash into its contents would be circular.

Private development and public snapshots have separate Git histories. Each release tag points to the corresponding commit in its own repository. Public source is explicitly selected and sanitized; private ancestry, credentials, runtime state, recordings and captures never belong in the public export. A private publication record links source commit, public commit, tag and manifest digest. Tags are not moved: corrections receive a new serial/tag.

Settings schema: `aurora_settings_registry_v1`. Recovery continues to read `aurora_input_recovery_v1` and `aurora_input_recovery_v2`; archive candidates are previews only and introduce no persisted migration. Future schema changes require explicit compatibility and migration notes.
