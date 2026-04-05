from unittest.mock import patch

from screenplay_tools.screenplay import ElementType

from theatremix.dca import _extract_page_number, generate_dca_cues


class TestExtractPageNumber:
    def test_standalone_note_absorbed_into_element(self, script_page_absorbed):
        """Standalone [[Page N]] notes get absorbed as inline refs in adjacent elements."""
        assert any(n.text == 'Page 42' for n in script_page_absorbed.notes)
        dialogue = next(
            e for e in script_page_absorbed.elements if e.type == ElementType.DIALOGUE
        )
        assert _extract_page_number(dialogue, script_page_absorbed.notes) == 42

    def test_non_page_note_returns_none(self, script_non_page_note):
        dialogue = next(
            e for e in script_non_page_note.elements if e.type == ElementType.DIALOGUE
        )
        assert _extract_page_number(dialogue, script_non_page_note.notes) is None

    def test_inline_note_in_dialogue(self, script_inline_page_in_dialogue):
        dialogue_elem = next(
            e
            for e in script_inline_page_in_dialogue.elements
            if e.type == ElementType.DIALOGUE
        )
        result = _extract_page_number(
            dialogue_elem, script_inline_page_in_dialogue.notes
        )
        assert result == 10

    def test_inline_note_in_action(self, script_inline_page_in_action):
        action_elem = next(
            e
            for e in script_inline_page_in_action.elements
            if e.type == ElementType.ACTION
        )
        result = _extract_page_number(action_elem, script_inline_page_in_action.notes)
        assert result == 5

    def test_element_without_notes_returns_none(self, script_alice_only):
        dialogue_elem = next(
            e for e in script_alice_only.elements if e.type == ElementType.DIALOGUE
        )
        assert _extract_page_number(dialogue_elem, script_alice_only.notes) is None

    def test_multiple_inline_page_notes_returns_last(self, script_multiple_page_notes):
        dialogue_elem = next(
            e
            for e in script_multiple_page_notes.elements
            if e.type == ElementType.DIALOGUE
        )
        result = _extract_page_number(dialogue_elem, script_multiple_page_notes.notes)
        assert result == 4


class TestGenerateDcaCues:
    """Tests for the full DCA cue generation pipeline."""

    MOCK_CHANNELS = {'Alice': '1', 'Bob': '2', 'Charlie': '3'}

    def _generate(self, script, channels=None, max_ahead=7):
        if channels is None:
            channels = self.MOCK_CHANNELS
        with patch('theatremix.dca.get_character_channels', return_value=channels):
            return generate_dca_cues(script, 'dummy.db', max_dialogues_ahead=max_ahead)

    def _get_dca_info(self, cue):
        """Extract non-None DCA data from a cue as {dca_num: (channels, label)}."""
        info = {}
        for j in range(1, 13):
            ch = getattr(cue, f'dca{j:02d}Channels')
            lb = getattr(cue, f'dca{j:02d}Label')
            if ch is not None or lb is not None:
                info[j] = (ch, lb)
        return info

    def test_single_character_unmute(self, script_alice_only):
        cues = self._generate(script_alice_only)
        assert len(cues) == 1
        info = self._get_dca_info(cues[0])
        assert 1 in info
        assert info[1] == ('1', 'Alice')

    def test_two_characters_get_different_dcas(self, script_alice_bob_alice):
        cues = self._generate(script_alice_bob_alice)
        info0 = self._get_dca_info(cues[0])
        assert info0[1] == ('1', 'Alice')

        info1 = self._get_dca_info(cues[1])
        assert 2 in info1
        assert info1[2] == ('2', 'Bob')

    def test_scene_change_mutes_characters(self, script_alice_scene_change_bob):
        cues = self._generate(script_alice_scene_change_bob)
        cue_names = [c.name for c in cues]
        assert any('Scene Change' in (n or '') for n in cue_names)

    def test_character_not_muted_if_speaks_first_in_new_scene(
        self, script_alice_scene_change_alice
    ):
        cues = self._generate(script_alice_scene_change_alice)
        cue_names = [c.name for c in cues]
        assert not any('Scene Change' in (n or '') for n in cue_names)

    def test_mute_after_lookahead_window(self, script_four_extras):
        channels = {'Alice': '1'}
        for i in range(4):
            channels[f'Extra{chr(65 + i)}'] = str(i + 10)

        cues = self._generate(script_four_extras, channels=channels, max_ahead=3)
        mute_cues = [c for c in cues if '-Alice' in (c.name or '')]
        assert len(mute_cues) >= 1

    def test_page_numbers_from_standalone_notes(self, script_page_standalone):
        cues = self._generate(script_page_standalone)
        assert cues[0].name.startswith('p5 ')

    def test_page_numbers_from_inline_notes(self, script_page_inline):
        cues = self._generate(script_page_inline)
        bob_cue = next(c for c in cues if 'Bob' in (c.name or ''))
        assert 'p6 ' in bob_cue.name

    def test_dca_reuse_after_mute(self, script_alice_bob_alice):
        cues = self._generate(script_alice_bob_alice, max_ahead=1)
        for cue in cues:
            for j in range(1, 13):
                ch = getattr(cue, f'dca{j:02d}Channels')
                if ch is not None:
                    assert isinstance(ch, str)

    def test_character_without_channel_gets_label_only(self, script_alice_only):
        cues = self._generate(script_alice_only, channels={})
        info = self._get_dca_info(cues[0])
        assert 1 in info
        assert info[1] == (None, 'Alice')

    def test_empty_script_returns_no_cues(self, parse):
        script = parse('')
        cues = self._generate(script)
        assert cues == []

    def test_sequential_cue_numbering(self, script_alice_bob_charlie):
        cues = self._generate(script_alice_bob_charlie)
        numbers = [c.number for c in cues]
        assert numbers == list(range(1, len(cues) + 1))
