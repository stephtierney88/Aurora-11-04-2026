# Aurora maintenance and continuity

This compatibility reference summarizes maintenance practice; historical private chat notes are not shipped. Repository [AGENTS](../../AGENTS.md), [AI guide](../../README_FOR_AI.md) and the [capability commitment](../../docs/notes/aurora_capability_compatibility.md) own the current workflow.

Use maps/catalogs before broad source reads. Keep one shared settings/admission/receipt authority and preserve legacy options. Distinguish requested, admitted, submitted, completed, cancelled and uncertain. An uncertain side effect must be inspected before retry; request IDs and receipts are evidence, not automatic permission to replay. Record observed state, scope, validation and rollback. Track exact owned processes/workspaces and clean only those resources. Keep credentials, runtime logs and captures out of source control.

Planned durable recovery, versioned memory and decision replay are not enabled by this note. Follow the [current roadmap](../../docs/notes/aurora_runtime_roadmap.md) and update implemented function skeletons only from source.
