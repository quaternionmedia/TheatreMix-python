from screenplay_tools.screenplay import ElementType

from theatremix.script import (
    split_characters,
    speaks_within,
    get_characters,
    get_line_preview_start,
    get_line_preview_end,
)


class TestSplitCharacters:
    def test_single_uppercase(self):
        assert split_characters('ALICE') == ['Alice']

    def test_dual_characters(self):
        assert split_characters('ALICE & BOB') == ['Alice', 'Bob']

    def test_removes_parenthetical(self):
        assert split_characters('ALICE (V.O.)') == ['Alice ']

    def test_preserves_lowercase_names(self):
        assert split_characters('Dr. Seuss') == ['Dr. Seuss']

    def test_multi_word_uppercase(self):
        assert split_characters('CAT IN THE HAT') == ['Cat In The Hat']

    def test_dual_with_parenthetical(self):
        result = split_characters("ALICE (CONT'D) & BOB")
        assert len(result) == 2
        assert 'Bob' in result


class TestSpeaksWithin:
    def test_character_speaks_next(self, script_alice_bob_alice):
        elements = script_alice_bob_alice.elements
        alice_idx = next(
            i
            for i, e in enumerate(elements)
            if e.type == ElementType.CHARACTER and e.name == 'ALICE'
        )
        remaining = elements[alice_idx + 1 :]
        assert speaks_within(remaining, 'Alice', n=7) is True

    def test_character_not_in_window(self, script_many_extras):
        elements = script_many_extras.elements
        alice_idx = next(
            i
            for i, e in enumerate(elements)
            if e.type == ElementType.CHARACTER and e.name == 'ALICE'
        )
        remaining = elements[alice_idx + 1 :]
        assert speaks_within(remaining, 'Alice', n=7) is False

    def test_stops_at_scene_heading(self, script_alice_scene_change_alice):
        elements = script_alice_scene_change_alice.elements
        alice_idx = next(
            i
            for i, e in enumerate(elements)
            if e.type == ElementType.CHARACTER and e.name == 'ALICE'
        )
        remaining = elements[alice_idx + 1 :]
        assert speaks_within(remaining, 'Alice', n=7) is False

    def test_skip_first(self, script_alice_bob):
        elements = script_alice_bob.elements
        char_idx = next(
            i for i, e in enumerate(elements) if e.type == ElementType.CHARACTER
        )
        remaining = elements[char_idx:]
        # Without skip_first, ALICE is found immediately
        assert speaks_within(remaining, 'Alice', n=7, skip_first=False) is True
        # With skip_first, ALICE's first occurrence is skipped
        assert speaks_within(remaining, 'Alice', n=7, skip_first=True) is False

    def test_empty_book(self):
        assert speaks_within([], 'Alice', n=7) is False


class TestGetCharacters:
    def test_extracts_unique_sorted(self, script_alice_bob_alice):
        result = get_characters(script_alice_bob_alice)
        assert result == ['Alice', 'Bob']

    def test_dual_characters(self, script_dual_characters):
        result = get_characters(script_dual_characters)
        assert 'Alice' in result
        assert 'Bob' in result


class TestGetLinePreview:
    def test_start_short_line(self, script_alice_only):
        elements = script_alice_only.elements
        char_idx = next(
            i for i, e in enumerate(elements) if e.type == ElementType.CHARACTER
        )
        result = get_line_preview_start(elements[char_idx + 1 :])
        assert result == 'Hello!'

    def test_start_truncates_long_line(self, script_long_dialogue):
        elements = script_long_dialogue.elements
        char_idx = next(
            i for i, e in enumerate(elements) if e.type == ElementType.CHARACTER
        )
        result = get_line_preview_start(elements[char_idx + 1 :], length=40)
        assert result == 'A' * 40 + '...'
        assert len(result) == 43

    def test_end_short_line(self, script_alice_only):
        result = get_line_preview_end(script_alice_only.elements)
        assert result == 'Hello!'

    def test_end_truncates_long_line(self, script_long_dialogue):
        result = get_line_preview_end(script_long_dialogue.elements, length=40)
        assert result == '...' + 'A' * 40

    def test_start_returns_none_if_no_dialogue(self, script_action_only):
        action_elems = [
            e for e in script_action_only.elements if e.type == ElementType.ACTION
        ]
        result = get_line_preview_start(action_elems)
        assert result is None

    def test_end_returns_none_if_no_dialogue(self, script_action_only):
        action_elems = [
            e for e in script_action_only.elements if e.type == ElementType.ACTION
        ]
        result = get_line_preview_end(action_elems)
        assert result is None
