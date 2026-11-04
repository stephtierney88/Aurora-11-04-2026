# OBS observation adapter — deferred proof

Status: September 5, 2026. The local `obs_readonly_client.py`,
`obs_readonly_mcp_server.py`, launcher and eleven tests are pre-existing,
uncommitted work. Unit coverage is present; a real authenticated OBS session has
not been proved by this task. This reference fills the previously missing map
entry without claiming activation readiness.

The user explicitly postponed that proof behind Aurora's command admission,
control responsiveness, AI command contracts, GUI quality and measured
performance work. Preserve the implementation. When resumed, validate connection,
scenes/sources, recording state, unavailable/partial behavior and provenance
against a real OBS instance, then expand this pack with verified usage.

The intended scope is observation; no OBS mutation authority is added here.
Current work order: [Aurora runtime roadmap](../notes/aurora_runtime_roadmap.md).
