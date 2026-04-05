from sqlmodel import Session
import re
from screenplay_tools.screenplay import ElementType, Script, Section

from .models import Cue
from .db import CueDatabase
from .script import (
    open_script,
    split_characters,
    speaks_within,
    get_character_channels,
    get_line_preview_start,
    get_line_preview_end,
)


def generate_dca_cues(
    script: Script, db_path: str, max_dialogues_ahead: int = 7
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
        if element.type == ElementType.NOTE:
            if re.match(r'^Page \d+$', element.text):
                page = int(re.search(r'\d+', element.text).group())
                continue

        # Handle scene transitions - mute all active characters
        if element.type == ElementType.HEADING:
            # Check if any current active character speaks first in this scene
            first_speakers = set()
            remaining_script = script.elements[i + 1 :]
            for future_elem in remaining_script:
                if future_elem.type == ElementType.CHARACTER:
                    chars = split_characters(future_elem.name)
                    first_speakers.update(char.strip() for char in chars)
                    break
                elif future_elem.type == ElementType.HEADING:
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
        if element.type == ElementType.CHARACTER:
            characters = split_characters(element.name)
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
    from .script import (
        open_script,
        split_characters,
        speaks_within,
        get_character_channels,
    )

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
        help='Path to .tmix database file',
    )
    args = parser.parse_args()

    script = open_script(args.script)
    cues = generate_dca_cues(script, args.database)
    print(f"Generated {len(cues)} DCA cues\n")
    print(cues[:1])

    with Session(CueDatabase(args.database).engine) as session:
        session.add_all(cues[:1])
        session.commit()
