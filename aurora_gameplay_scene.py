"""Bounded, provenance-aware text scene inference; never claims visual verification."""
from __future__ import annotations

import math
import re

SCENES = ("title", "main_menu", "dialog", "overworld", "battle", "transition", "unknown")
MAX_AGE_SECONDS = 120
MAX_AGE_TURNS = 1
HINTS = {
    "title": ("title screen", "press start", "press any button"),
    "main_menu": ("main menu", "continue", "new game", "save file"),
    "dialog": ("textbox", "text box", "dialog", "dialogue", "speech box", "npc text"),
    "overworld": ("overworld", "bedroom", "stairs", "player sprite", "building interior", "doorway", "walking", "town", "route", "cave"),
    "battle": ("battle", "fight", "choose a move", "move selection", "hp", "pp"),
    "transition": ("loading", "fading", "screen transition", "black screen", "white flash", "warp"),
}
ALLOWED_SOURCES = {"assistant_observation", "assistant_scene"}
NON_OBSERVATION = re.compile(r"\b(?:previously|earlier|yesterday|last turn|used to|was|were|will|would|might|could|should|plan|planning|goal|if|rejected|receipt|policy|classified|classifier)\b", re.I)
NEGATION = re.compile(r"\b(?:no|not|without|neither|never|isn't|isnt|aren't|wasn't|cannot|can't|lack(?:s|ing)?|absent)\b", re.I)


def classify_scene(records, *, now, turn, operating_context="unknown"):
    scores = {scene: 0 for scene in SCENES}
    evidence = {scene: [] for scene in SCENES}
    rejected, accepted, negated, explicit = [], [], set(), set()
    for row in list(records or [])[-8:]:
        reason = ""
        if not isinstance(row, dict) or row.get("source") not in ALLOWED_SOURCES:
            reason = "non_observation_source"
        else:
            stamp, observed_turn = row.get("observed_at"), row.get("turn")
            if type(stamp) not in (int, float) or not math.isfinite(stamp) or type(observed_turn) is not int:
                reason = "missing_freshness"
            elif not 0 <= now - stamp <= MAX_AGE_SECONDS or not 0 <= turn - observed_turn <= MAX_AGE_TURNS:
                reason = "stale_or_future_observation"
        if reason:
            rejected.append(reason)
            continue
        accepted.append({"source": row["source"], "turn": row["turn"], "observed_at": row["observed_at"]})
        text = str(row.get("text", ""))[:4000].lower()
        if row["source"] == "assistant_scene":
            if text.strip() in SCENES:
                explicit.add(text.strip())
            else:
                rejected.append("invalid_scene_label")
            continue
        # NPC dialogue is displayed content, not a claim about the current
        # interface (e.g. Oak: "You've never had a Pokemon battle before").
        text = re.sub(r'"[^"\n]*"|“[^”\n]*”', " ", text)
        for clause in re.split(r"[.!?;\n]|\bbut\b|\bhowever\b", text):
            if NON_OBSERVATION.search(clause):
                rejected.append("historical_hypothetical_or_feedback_clause")
                continue
            for scene, hints in HINTS.items():
                for hint in hints:
                    for match in re.finditer(r"(?<!\w)" + re.escape(hint) + r"(?!\w)", clause):
                        before = " ".join(clause[:match.start()].split()[-6:])
                        after = clause[match.end():]
                        denied = NEGATION.search(before) or re.match(r"\s+(?:(?:is|are|has)\s+)?(?:not|absent|over|ended|finished|closed|gone|disappeared)\b", after)
                        if denied:
                            negated.add(scene)
                            continue
                        if hint not in evidence[scene]:
                            evidence[scene].append(hint)
                            scores[scene] += 1 if hint in {"hp", "pp", "continue", "route"} else 3
    candidates = {scene for scene in SCENES if scores[scene] >= 3}
    conflicts = []
    # A battle's text box is compatible UI evidence; unrelated scenes are not.
    if candidates and candidates <= {"battle", "dialog"} and "battle" in candidates:
        candidates = {"battle"}
    compatibility_notes = []
    if explicit == {"dialog"} and candidates and candidates <= {"overworld", "dialog"}:
        candidates = {"dialog"}
        compatibility_notes.append("dialog_overlay_with_current_location_evidence")
    if explicit == {"dialog"} and candidates == {"battle"}:
        # Battle tutorials/announcements have a dialogue overlay. This is not
        # contradictory evidence about leaving the battle itself.
        explicit = {"battle"}
        compatibility_notes.append("dialog_overlay_with_current_battle_evidence")
    if len(explicit) > 1 or (explicit and "unknown" not in explicit and any(s in negated for s in explicit)):
        conflicts.append("contradictory_explicit_scene")
    if explicit and "unknown" not in explicit and candidates - explicit:
        conflicts.append("scene_label_conflicts_with_observation")
    if len(candidates) > 1:
        conflicts.append("multiple_current_scenes")
    if candidates & negated:
        conflicts.append("positive_and_negative_scene_evidence")
    scene = "unknown"
    if not conflicts:
        if explicit:
            scene = next(iter(explicit))
        elif len(candidates) == 1:
            scene = next(iter(candidates))
    if operating_context not in {"unknown", "game"}:
        scene = "unknown"
        rejected.append("non_game_operating_context")
    return {"scene": scene, "summary": "; ".join(conflicts) if conflicts else
            (f"current model-reported {scene}; not visually verified" if scene != "unknown" else "no unambiguous fresh scene evidence"),
            "policy": "evidence", "scores": scores, "evidence": evidence, "conflicts": conflicts,
            "accepted_sources": accepted, "rejected_reasons": sorted(set(rejected)),
            "compatibility_notes": compatibility_notes,
            "negated_scenes": sorted(negated), "visually_verified": False,
            "freshness_basis": "model_report_time_and_turn; capture freshness is not established"}
