# Game Profile Reference

## Purpose
- Summarize the supported Aurora Pokemon game profiles and the practical differences that matter during testing.

## Profiles

### FireRed
- Canonical profile id: `firered`
- Current default for live gameplay soaks
- Preferred when visual readability matters
- Save-state note: use emulator save/load slots manually; do not assume in-game `SAVE` is the main persistence path for soak validation
- Title and scene interpretation should expect GBA-era menus, overworld color, shoreline, building roofs, and richer palette cues

### Blue
- Canonical profile id: `blue`
- Secondary profile for regression and profile-plumbing validation
- Can be useful for older route logic and simpler scenes, but is harder for weak vision models
- If using Blue, keep save-state habits explicit and avoid assuming they match FireRed exactly unless verified on the current emulator setup

## Runtime surface
- Environment: `AURORA_GAME_PROFILE=firered|blue`
- Commands:
- `SET_GAME_PROFILE(firered|blue)`
- `SHOW_GAME_PROFILE()`
- Exported state:
- `modes.game_profile`
- `modes.game_profile_source`
- `planning.game_profile_label`
- `planning.game_profile_save_note`

## Selection guidance
- Use FireRed for primary live testing.
- Use Blue to confirm the profile plumbing still works and that Blue-specific assumptions have not leaked into FireRed or vice versa.
- If the live ROM and the runtime profile disagree, prefer fixing the profile before judging gameplay behavior.
