import unittest

from aurora_gameplay_scene import classify_scene


class SceneTests(unittest.TestCase):
    def classify(self, text="", *, records=None, **kwargs):
        if records is None:
            records = [{"source": "assistant_observation", "text": text, "turn": 7, "observed_at": 1000}]
        return classify_scene(records, now=1001, turn=7, operating_context="game", **kwargs)

    def test_bedroom_upper_and_negated_battle(self):
        for text in ("The bedroom stairs are at upper right.", "The bedroom has no battle interface.",
                     "Bedroom visible; no HP or PP display.", "No battle interface, but the bedroom is visible."):
            with self.subTest(text=text):
                self.assertEqual(self.classify(text)["scene"], "overworld")

    def test_substrings_and_weak_ui_words_are_not_a_battle(self):
        for text in ("upper right", "shopping", "support", "HP", "PP", "HP and PP"):
            self.assertEqual(self.classify(text)["scene"], "unknown")

    def test_current_battle_and_dialog_can_coexist(self):
        self.assertEqual(self.classify("A wild battle is visible. A text box shows the opponent.")["scene"], "battle")
        result = self.classify(records=[
            {"source": "assistant_scene", "text": "battle", "turn": 7, "observed_at": 1000},
            {"source": "assistant_observation", "text": "Wild battle, Fight and a text box are visible", "turn": 7, "observed_at": 1000}])
        self.assertEqual(result["scene"], "battle")

    def test_historical_and_future_battles_do_not_override_observation(self):
        result = self.classify("Earlier a battle was active. We should fight later. The bedroom is visible.")
        self.assertEqual(result["scene"], "overworld")
        self.assertIn("historical_hypothetical_or_feedback_clause", result["rejected_reasons"])

    def test_explicit_dialog_overlay_does_not_obscure_current_battle(self):
        rows = [
            {"source": "assistant_scene", "text": "dialog", "turn": 7, "observed_at": 1000},
            {"source": "assistant_observation", "text": "The battle tutorial text box is visible beside Charmander and Squirtle.", "turn": 7, "observed_at": 1000}]
        result = self.classify(records=rows)
        self.assertEqual(result["scene"], "battle")
        self.assertIn("dialog_overlay_with_current_battle_evidence", result["compatibility_notes"])
        rows[0]["text"] = "overworld"
        self.assertEqual(self.classify(records=rows)["scene"], "unknown")

    def test_goals_receipts_and_unstamped_history_are_excluded(self):
        rows = [{"source": source, "text": "battle", "observed_at": 1000, "turn": 7}
                for source in ("goal", "receipt", "last_prompt", "route_plan")]
        rows.append({"source": "assistant_observation", "text": "battle"})
        self.assertEqual(self.classify(records=rows)["scene"], "unknown")

    def test_stale_and_future_observations_are_excluded(self):
        for stamp, turn in ((1, 7), (1002, 7), (1000, 4), (1000, 8), (float("nan"), 7)):
            result = self.classify(records=[{"source": "assistant_scene", "text": "battle", "observed_at": stamp, "turn": turn}])
            self.assertEqual(result["scene"], "unknown")

    def test_conflicts_are_unknown_with_explanations(self):
        result = self.classify("A battle is visible. The bedroom stairs are visible.")
        self.assertEqual(result["scene"], "unknown")
        self.assertIn("multiple_current_scenes", result["conflicts"])

    def test_explicit_scene_conflicts_with_current_negation(self):
        result = self.classify(records=[
            {"source": "assistant_scene", "text": "battle", "observed_at": 1000, "turn": 7},
            {"source": "assistant_observation", "text": "No battle interface; bedroom visible", "observed_at": 1000, "turn": 7}])
        self.assertEqual(result["scene"], "unknown")
        self.assertTrue(result["conflicts"])

    def test_explicit_unknown_is_preserved(self):
        result = self.classify(records=[{"source": "assistant_scene", "text": "unknown", "observed_at": 1000, "turn": 7}])
        self.assertEqual(result["scene"], "unknown")
        self.assertFalse(result["visually_verified"])

    def test_current_menu_and_transition(self):
        self.assertEqual(self.classify("Main menu shows Continue and New Game")["scene"], "main_menu")
        self.assertEqual(self.classify("A black screen is fading")["scene"], "transition")

    def test_finished_battle_and_negated_suffix(self):
        for text in ("Battle has ended. Bedroom visible.", "Battle not visible. Bedroom visible.",
                     "No longer in battle. Bedroom visible."):
            self.assertEqual(self.classify(text)["scene"], "overworld")

    def test_quoted_tutorial_is_not_a_negative_scene_claim(self):
        for quote in ('“You’ve never had a POKéMON battle before, have you?”', '"You have never had a battle before?"'):
            rows = [{"source": "assistant_scene", "text": "battle", "observed_at": 1000, "turn": 7},
                    {"source": "assistant_observation", "text": 'Oak shows ' + quote + ' Bulbasaur has 20/20 HP.', "observed_at": 1000, "turn": 7}]
            self.assertEqual(self.classify(records=rows)['scene'], 'battle')

    def test_closed_dialog_does_not_override_overworld(self):
        rows = [{"source": "assistant_scene", "text": "overworld", "observed_at": 1000, "turn": 7},
                {"source": "assistant_observation", "text": 'The dialogue has closed. Red stands below Oak.', "observed_at": 1000, "turn": 7}]
        self.assertEqual(self.classify(records=rows)['scene'], 'overworld')

    def test_dialog_overlay_can_include_location(self):
        rows = [{"source": "assistant_scene", "text": "dialog", "observed_at": 1000, "turn": 7},
                {"source": "assistant_observation", "text": 'At Pallet Town, Oak says “Hey! Wait!”', "observed_at": 1000, "turn": 7}]
        self.assertEqual(self.classify(records=rows)['scene'], 'dialog')

    def test_battle_label_with_generic_tutorial_or_result_dialogue(self):
        for text in ("Gary's defeat dialogue remains unchanged.",
                     "The dialogue remains on RED with a continuation arrow. Bulbasaur is at 20/20 HP.",
                     "Gary's defeat dialogue is unchanged. Confirm is held because the scene classifier conflicts with the visible battle screen."):
            rows = [{"source": "assistant_scene", "text": "battle", "observed_at": 1000, "turn": 7},
                    {"source": "assistant_observation", "text": text, "observed_at": 1000, "turn": 7}]
            result = self.classify(records=rows)
            self.assertEqual(result['scene'], 'battle')
            self.assertIn('dialog_overlay_with_reported_battle', result['compatibility_notes'])
            self.assertFalse(result['visually_verified'])

    def test_battle_dialogue_compatibility_does_not_hide_real_conflicts(self):
        for text in ("The dialogue is visible. No battle interface.",
                     "Dialogue visible. Bedroom stairs are visible.",
                     "Dialogue visible. No text box is visible."):
            rows = [{"source": "assistant_scene", "text": "battle", "observed_at": 1000, "turn": 7},
                    {"source": "assistant_observation", "text": text, "observed_at": 1000, "turn": 7}]
            self.assertEqual(self.classify(records=rows)['scene'], 'unknown')


if __name__ == "__main__":
    unittest.main()
