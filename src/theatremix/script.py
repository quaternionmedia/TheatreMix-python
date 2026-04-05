from sqlmodel import Session, select
from fountain import fountain
import re

from .models import Cue, Profile, Ensemble
from .db import CueDatabase

# from rich import print

DATABASE = 'mix/seuss.tmix'


def open_script(
    file_path: str,
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
