from sqlmodel import Session, select
from fountain import fountain
import re

from .models import Cue, Profile, Ensemble
from .db import CueDatabase

# from rich import print

DATABASE = 'mix/seuss.tmix'


def open_script(
    file_path: str = '../seussical/scripts/seussical.fountain',
) -> fountain.Fountain:
    """Open and parse a Fountain script from a file path."""
    with open(file_path, 'r') as file:
        return fountain.Fountain(file.read())


def split_characters(characters: str) -> list[str]:
    """Clean and split character headings"""
    # Remove parenthesis
    characters = re.sub(r'\([^)]*\)', '', characters)
    # split the characters by '&'
    # If it contains lowercase letters (e.g., "Dr. Seuss"), keep as is
    # Otherwise, title case each character name
    return [c if re.search(r'[a-z]', c) else c.title() for c in characters.split(' & ')]


def speaks_within(book, character, n: int = 7, skip_first: bool = False) -> bool:
    """Check if character speaks within next n dialogue blocks or before scene change.

    Args:
        book: List of script elements to search
        character: Character name to look for
        n: Number of dialogue blocks to look ahead
        skip_first: If True, don't count the first dialogue block in the search

    Returns:
        True if character speaks within window, False otherwise
    """
    dialogues = 0
    first_skipped = not skip_first
    for i, element in enumerate(book):
        if dialogues >= n:
            return False
        if element.element_type == 'Scene Heading':
            return False
        if element.element_type == 'Character':
            if not first_skipped:
                first_skipped = True
                continue
            characters = split_characters(element.element_text)
            if character in characters:
                return True
            dialogues += 1
    return False


def get_characters(script):
    characters = set()
    for element in script.elements:
        if element.element_type == 'Character':
            chars = split_characters(element.element_text)
            for char in chars:
                characters.add(char.strip())
    characters = sorted(list(characters))
    return characters


def get_line_preview_start(script, length=40):
    """Get a starting preview of the dialogue line following the character element"""
    # look for the next Dialogue element
    for i in range(len(script)):
        if script[i].element_type == 'Dialogue':
            line = script[i].element_text
            if len(line) > length:
                return line[:length] + '...'
            else:
                return line


def get_line_preview_end(script, length=40):
    """Get an ending preview of the dialogue line following the character element"""
    # look for the next Dialogue element from the end
    for i in range(len(script) - 1, -1, -1):
        if script[i].element_type == 'Dialogue':
            line = script[i].element_text
            if len(line) > length:
                return '...' + line[-length:]
            else:
                return line


def get_character_channels(db_path: str = DATABASE) -> dict[str, str]:
    """Load character to channel mapping from database.

    For individual characters, returns their single channel number.
    For ensemble groups, returns comma-separated list of all member channels.

    Args:
        db_path: Path to the .tmix database file

    Returns:
        Dictionary mapping character names to channel numbers (as strings)
    """
    db = CueDatabase(db_path, create_schema=False, init_config=False)
    character_channels = {}

    with Session(db.engine) as session:
        # Load characters from Profile table
        profiles = session.exec(select(Profile)).all()
        for profile in profiles:
            character_channels[profile.name] = str(profile.channel)
        # Load ensemble groups and map to comma-separated channel lists
        ensembles = session.exec(select(Ensemble)).all()
        for ensemble in ensembles:
            character_channels[ensemble.name] = ensemble.channels

    return character_channels


def generate_dca_cues(
    script: fountain.Fountain, db_path: str = DATABASE, max_dialogues_ahead: int = 7
) -> list[Cue]:
    """Generate the list of cues for DCA muting.

    This function parses a Fountain script and creates a list of Cue objects
    with DCA (Digital Control Assignment) assignments for character microphones.

    Logic:
    - Characters are unmuted when they first speak in a scene
    - Characters are muted when they won't speak within the next 7 dialogue blocks
    - Scene transitions mute all active characters (unless they speak first in new scene)
    - DCAs 1-12 are dynamically assigned and reused as characters are muted

    Args:
        script: Parsed Fountain script object
        db_path: Path to database file with character/channel mappings

    Returns:
        List of Cue objects with DCA assignments for muting/unmuting
    """
    # Load character to channel mapping from database
    character_channels = get_character_channels(db_path)

    cues = []
    active_mics = set()  # Characters currently unmuted
    # NOTE: DCA assignment strategy - currently dynamic reuse of available DCAs.
    # To implement consistent DCA per character, replace this with a character->DCA mapping dict
    dca_assignments = {}  # Maps character name -> DCA number (1-12)
    available_dcas = set(range(1, 13))  # DCAs 1-12 available for assignment
    page = 0
    cue_number = 1

    # Track current DCA state to copy to next cue
    current_dca_state = {
        'channels': {i: None for i in range(1, 13)},  # DCA number -> channel(s)
        'labels': {i: None for i in range(1, 13)},  # DCA number -> label
    }

    for i, element in enumerate(script.elements):
        # Track page numbers from comments
        if element.element_type == 'Comment':
            if re.match(r'^Page \d+$', element.element_text):
                page = int(re.search(r'\d+', element.element_text).group())
                continue

        # Handle scene transitions - mute all active characters
        if element.element_type == 'Scene Heading':
            # Check if any current active character speaks first in this scene
            first_speakers = set()
            remaining_script = script.elements[i + 1 :]
            for future_elem in remaining_script:
                if future_elem.element_type == 'Character':
                    chars = split_characters(future_elem.element_text)
                    first_speakers.update(char.strip() for char in chars)
                    break
                elif future_elem.element_type == 'Scene Heading':
                    break

            # Mute characters who won't speak first in new scene
            characters_to_mute = active_mics - first_speakers
            if characters_to_mute:
                # Create single cue with all mutes for scene change
                mute_names = ', '.join(sorted(characters_to_mute))
                cue = Cue(
                    number=cue_number,
                    point=0,
                    name=f"p{page} -{mute_names}- Scene Change - {get_line_preview_end(script.elements[:i], 30)}",
                )

                # Copy all current DCA states to this cue
                for dca_i in range(1, 13):
                    if current_dca_state['channels'][dca_i] is not None:
                        setattr(
                            cue,
                            f'dca{dca_i:02d}Channels',
                            current_dca_state['channels'][dca_i],
                        )
                    if current_dca_state['labels'][dca_i] is not None:
                        setattr(
                            cue,
                            f'dca{dca_i:02d}Label',
                            current_dca_state['labels'][dca_i],
                        )

                # Apply all mute changes
                for character in characters_to_mute:
                    dca_num = dca_assignments[character]
                    channel = character_channels.get(character, '')

                    # Update this DCA's state (mute/clear both channels and labels)
                    if channel:
                        setattr(cue, f'dca{dca_num:02d}Channels', None)
                        current_dca_state['channels'][dca_num] = None
                    setattr(cue, f'dca{dca_num:02d}Label', None)
                    current_dca_state['labels'][dca_num] = None

                    # Free up the DCA and remove from active
                    available_dcas.add(dca_num)
                    del dca_assignments[character]
                    active_mics.discard(character)

                cues.append(cue)
                cue_number += 1

            continue

        # Handle character dialogue
        if element.element_type == 'Character':
            characters = split_characters(element.element_text)
            remaining_script = script.elements[i + 1 :]

            # Collect all DCA changes for this dialogue block
            characters_to_unmute = []
            characters_to_mute = []

            # Process each character in this dialogue block
            for character in characters:
                character = character.strip()[
                    :12
                ]  # TODO: Fix character name length handling

                # Track character if not already active
                if character not in active_mics:
                    # Assign an available DCA
                    if available_dcas:
                        dca_num = min(available_dcas)  # Use lowest available DCA
                        available_dcas.remove(dca_num)
                    else:
                        # All DCAs in use - reuse DCA 1 (fallback)
                        # This shouldn't happen with proper lookahead muting
                        dca_num = 1

                    dca_assignments[character] = dca_num
                    characters_to_unmute.append(character)
                    active_mics.add(character)

            # Check all currently active characters to see if they should be muted
            # Exclude characters who are speaking in this current block
            currently_speaking = set(char.strip() for char in characters)
            for active_character in active_mics.copy():
                # Don't check characters who are speaking right now
                if active_character in currently_speaking:
                    continue
                # Check if this character speaks within the next 7 dialogue blocks
                # Pass remaining script after current element
                if not speaks_within(
                    remaining_script,
                    active_character,
                    n=max_dialogues_ahead,
                    skip_first=False,
                ):
                    characters_to_mute.append(active_character)

            # Create a single cue for all DCA changes in this block
            if characters_to_unmute or characters_to_mute:
                # Build cue name with +/- prefixes per character
                unmute_names = (
                    ', '.join(f'+{char}' for char in characters_to_unmute)
                    if characters_to_unmute
                    else ''
                )
                mute_names = (
                    ', '.join(f'-{char}' for char in characters_to_mute)
                    if characters_to_mute
                    else ''
                )

                if unmute_names and mute_names:
                    cue_name = f'p{page} {unmute_names} {mute_names}: "{get_line_preview_start(remaining_script, 30)}"'
                elif unmute_names:
                    cue_name = f'p{page} {unmute_names}: "{get_line_preview_start(remaining_script, 30)}"'
                else:
                    cue_name = f'p{page} {mute_names}: "{get_line_preview_start(remaining_script, 30)}"'

                cue = Cue(
                    number=cue_number,
                    point=0,
                    name=cue_name,
                )

                # Copy all current DCA states to this cue
                for dca_i in range(1, 13):
                    if current_dca_state['channels'][dca_i] is not None:
                        setattr(
                            cue,
                            f'dca{dca_i:02d}Channels',
                            current_dca_state['channels'][dca_i],
                        )
                    if current_dca_state['labels'][dca_i] is not None:
                        setattr(
                            cue,
                            f'dca{dca_i:02d}Label',
                            current_dca_state['labels'][dca_i],
                        )

                # Apply all unmute changes
                for character in characters_to_unmute:
                    dca_num = dca_assignments[character]
                    channel = character_channels.get(character)

                    if channel:
                        setattr(cue, f'dca{dca_num:02d}Channels', channel)
                        current_dca_state['channels'][dca_num] = channel
                        # Also set label for ensembles (channels with commas) and individuals
                        setattr(cue, f'dca{dca_num:02d}Label', character)
                        current_dca_state['labels'][dca_num] = character
                    else:
                        setattr(cue, f'dca{dca_num:02d}Label', character)
                        current_dca_state['labels'][dca_num] = character

                # Apply all mute changes
                for character in characters_to_mute:
                    dca_num = dca_assignments[character]
                    channel = character_channels.get(character, '')

                    # Clear both channels and labels when muting
                    if channel:
                        setattr(cue, f'dca{dca_num:02d}Channels', None)
                        current_dca_state['channels'][dca_num] = None
                    setattr(cue, f'dca{dca_num:02d}Label', None)
                    current_dca_state['labels'][dca_num] = None

                    # Free up the DCA and remove from active
                    available_dcas.add(dca_num)
                    del dca_assignments[character]
                    active_mics.discard(character)

                cues.append(cue)
                cue_number += 1

    return cues


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='Generate DCA muting cues from a Fountain script'
    )
    parser.add_argument(
        '--script',
        default='../seussical/scripts/seussical.fountain',
        help='Path to Fountain script file (default: ../seussical/scripts/seussical.fountain)',
    )
    parser.add_argument(
        '--database',
        default=DATABASE,
        help=f'Path to .tmix database file (default: {DATABASE})',
    )
    args = parser.parse_args()

    script = open_script()
    cues = generate_dca_cues(script)
    print(f"Generated {len(cues)} DCA cues\n")
    print(cues[:1])

    with Session(CueDatabase(DATABASE).engine) as session:
        session.add_all(cues[:1])
        session.commit()
