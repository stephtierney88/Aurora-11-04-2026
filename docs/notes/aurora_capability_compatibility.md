# Aurora capability and compatibility commitment

Confirmed by the user 2026-09-06. Advanced AI is the primary operator. Broad capabilities and a large settings arsenal are deliberate product goals.

- Preserve existing commands, aliases, valid behaviors, modes, states and saved configuration. Do not remove a capability merely to reduce command count or simplify the GUI.
- Add new behaviors alongside the existing path, selectable through appropriate toggles, explicit modes, named profiles, configuration or searchable Advanced controls. Keep full-detail/raw access available; a compact presentation must not become a capability restriction.
- Use the shared typed settings authority for adopted settings, with command/CLI/GUI parity where applicable, effective value and source, scope, apply timing, maturity, versioned readback and rollback. Profiles expose their member changes.
- Keep visibility, capability enablement, execution permission, persistence, transport and scheduling distinct. Preserve older models, Chat Completions, the optional Responses path, reasoning modes, gameplay backends and indefinite-input capabilities.
- Correctness fixes should retain valid intended use. Reject malformed requests explicitly instead of silently dropping fields, changing meaning or partially claiming success. Record any intentional compatibility change, why it is necessary, and the migration or explicit alternative.
- Before closing a slice, verify command/alias and relevant configuration parity, meaningful regressions, observable before/after state, failure/cancellation recovery and cleanup. Existing files and unrelated work must survive.
- Roadmap H0–H5 is accepted as a staged adoption direction; individual experimental capabilities remain disabled until implemented and verified. Use the roadmap's current active queue for order. The older 4B4 -> 4C -> 4D foundation remains accepted work, not an instruction to override subsequent user-directed repairs or the capture/continuation priorities.

Read this commitment from current status, the roadmap, handoff and optionality references. Keep those reminders short and link here so the policy has one maintained source. This note does not enable a new runtime feature or change native-testing/Browser/OBS/Portal/Mac/SSH boundaries.
