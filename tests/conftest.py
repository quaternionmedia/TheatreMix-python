import pytest
from screenplay_tools.screenplay import Script

from theatremix.script import _LineTrackingParser


@pytest.fixture
def parse():
    """Return a helper that parses a Fountain string into a Script."""

    def _parse(text: str) -> Script:
        p = _LineTrackingParser()
        p.add_text(text)
        p.finalize()
        script = p.script
        script.element_source_lines = p.element_source_lines
        return script

    return _parse


# ---------------------------------------------------------------------------
# Reusable script fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def script_alice_only(parse):
    """Single character: ALICE says 'Hello!'"""
    return parse(
        '''
INT. ROOM - DAY

ALICE
Hello!
'''
    )


@pytest.fixture
def script_alice_bob(parse):
    """Two characters, no return: ALICE then BOB."""
    return parse(
        '''
INT. ROOM - DAY

ALICE
Hello!

BOB
Hi!
'''
    )


@pytest.fixture
def script_alice_bob_alice(parse):
    """ALICE, BOB, then ALICE again."""
    return parse(
        '''
INT. ROOM - DAY

ALICE
Hello!

BOB
Hi!

ALICE
How are you?
'''
    )


@pytest.fixture
def script_alice_bob_charlie(parse):
    """Three characters in sequence."""
    return parse(
        '''
INT. ROOM - DAY

ALICE
Hello!

BOB
Hi!

CHARLIE
Hey!
'''
    )


@pytest.fixture
def script_alice_scene_change_alice(parse):
    """ALICE speaks in two scenes separated by a heading."""
    return parse(
        '''
INT. ROOM - DAY

ALICE
Hello!

INT. OTHER ROOM - NIGHT

ALICE
I am here now.
'''
    )


@pytest.fixture
def script_alice_scene_change_bob(parse):
    """ALICE speaks, scene change, then BOB speaks."""
    return parse(
        '''
INT. ROOM - DAY

ALICE
Hello!

INT. OTHER ROOM - NIGHT

BOB
Hi there.
'''
    )


@pytest.fixture
def script_dual_characters(parse):
    """Dual character line: ALICE & BOB."""
    return parse(
        '''
INT. ROOM - DAY

ALICE & BOB
Together!
'''
    )


@pytest.fixture
def script_action_only(parse):
    """Scene with only action, no dialogue."""
    return parse(
        '''
INT. ROOM - DAY

Some action here.
'''
    )


@pytest.fixture
def script_long_dialogue(parse):
    """ALICE with a 60-character dialogue line."""
    return parse(
        f'''
INT. ROOM - DAY

ALICE
{'A' * 60}
'''
    )


@pytest.fixture
def script_many_extras(parse):
    """ALICE speaks, then 8 extras speak, then ALICE returns."""
    lines = ['INT. ROOM - DAY\n', 'ALICE\nHello!\n']
    for i in range(8):
        lines.append(f'EXTRA{chr(65 + i)}\nLine {i}!\n')
    lines.append('ALICE\nI am back!\n')
    return parse('\n'.join(lines))


@pytest.fixture
def script_four_extras(parse):
    """ALICE speaks, then 4 extras speak (no ALICE return)."""
    lines = ['INT. ROOM - DAY\n', 'ALICE\nHello!\n']
    for i in range(4):
        lines.append(f'EXTRA{chr(65 + i)}\nLine {i}!\n')
    return parse('\n'.join(lines))


@pytest.fixture
def script_page_standalone(parse):
    """Script with a standalone [[Page 5]] note before dialogue."""
    return parse(
        '''
[[Page 5]]

INT. ROOM - DAY

ALICE
Hello!
'''
    )


@pytest.fixture
def script_page_inline(parse):
    """Script with standalone page 5 and inline [[Page 6]] in dialogue."""
    return parse(
        '''
[[Page 5]]

INT. ROOM - DAY

ALICE
Start of a long speech [[Page 6]] and it keeps going.

BOB
Hi!
'''
    )


@pytest.fixture
def script_page_absorbed(parse):
    """Standalone [[Page 42]] absorbed into adjacent dialogue."""
    return parse('INT. ROOM - DAY\n\nALICE\nHello!\n[[Page 42]]\n\nBOB\nHi!\n')


@pytest.fixture
def script_non_page_note(parse):
    """Dialogue with a non-page inline note."""
    return parse('INT. ROOM - DAY\n\nALICE\nHello! [[Just a comment]]\n')


@pytest.fixture
def script_inline_page_in_dialogue(parse):
    """Dialogue with inline [[Page 10]]."""
    return parse(
        '''
INT. ROOM - DAY

ALICE
Hello there [[Page 10]] friend!
'''
    )


@pytest.fixture
def script_inline_page_in_action(parse):
    """Action with inline [[Page 5]]."""
    return parse(
        '''
INT. ROOM - DAY

Alice walks across the room [[Page 5]] and sits down.
'''
    )


@pytest.fixture
def script_multiple_page_notes(parse):
    """Dialogue with two inline page notes."""
    return parse(
        '''
INT. ROOM - DAY

ALICE
Start [[Page 3]] middle [[Page 4]] end.
'''
    )
