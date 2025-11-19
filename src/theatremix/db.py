"""SQLModel-based database integration for QLab cue management."""

from typing import Optional, List, Dict, Any
from pathlib import Path
from sqlmodel import Session, SQLModel, create_engine, select
from sqlalchemy import func

from .models import (
    Config,
    Cue,
    Profile,
    Position,
    Ensemble,
    Actor,
    ActorProfile,
    ActorGroup,
    SnippetCache,
    FXCache,
    SceneCache,
)


# Default configuration values
DEFAULT_CONFIG = {
    "targetConsole": "GLD-112",
    "designer": "Copilot",
    "venue": "Theatre",
    "dcas": "1,2,3,4,5,6,7,8",
    "channels": "1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16",
    "backupChannels": "",
    "fxAssigns": "1,2,3,4",
    "fxMutes": "1,2,3,4",
    "defaultFX": "-1",
    "snippetRecall": "0",
    "fxBusMap": "4=1104,1=1101,2=1102,3=1103",
    "buttonMap": "1=17,0=18",
    "muteButtonMap": "",
    "muteButtonAssignKeys": "",
    "profileSchemaVersion": "2",
    "qLabCues": "0",
    "consoleModel": "GLD-112",
    "consoleVersion": "1.61",
    "consoleIP": "192.168.1.1",
    "consoleMAC": "00:00:00:00:00:00",
    "autoConnect": "1",
    "enableChannelMonitoring": "0",
    "gangLR": "0",
    "gangLRChannels": "",
    "gangLRName": "Band",
    "gangLRColour": "11",
    "activeChannelHighlight": "1",
    "cueZeroSnippets": "",
    "minVersion": "3.1",
    "spareBackup": "0",
    "labelLR": "1",
    "labelTargetBus": "1410",
    "consoleMuteDCAUnassign": "0",
    "qLabPasscode": "",
    "suppressDCAMuteBackupSwitch": "0",
    "channelLevels": "1",
    "cueZeroResetLevels": "1",
    "sceneRecall": "0",
    "cueZeroScenes": "",
    "dimDCAFaders": "0",
    "qLabSuppressBack": "0",
    "qlclDyn1": "0",
    "cueZeroScenePoints": "",
    "dimDCAFadersSuppressColours": "0",
}


class CueDatabase:
    """SQLModel-based database manager for theatre cues."""

    def __init__(
        self, db_path: str, create_schema: bool = True, init_config: bool = True
    ):
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file
            create_schema: If True, create schema if it doesn't exist
            init_config: If True, initialize config table with defaults
        """
        self.db_path = Path(db_path)
        is_new = not self.db_path.exists()

        # Create engine with SQLite
        self.engine = create_engine(f"sqlite:///{self.db_path}")

        if create_schema and is_new:
            self._create_schema()
            if init_config:
                self._init_config()

    def _create_schema(self):
        """Create all tables in the database."""
        SQLModel.metadata.create_all(self.engine)

    def _init_config(self):
        """Initialize config table with default values."""
        with Session(self.engine) as session:
            for param, value in DEFAULT_CONFIG.items():
                config = Config(param=param, value=value)
                session.add(config)
            session.commit()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def close(self):
        """Close database connection."""
        if hasattr(self, 'engine'):
            self.engine.dispose()

    def get_next_cue_number(self) -> tuple[int, int]:
        """Get the next available cue number and point.

        Returns:
            Tuple of (number, point) where point is incremented by 10
        """
        with Session(self.engine) as session:
            result = session.exec(
                select(func.max(Cue.number), func.max(Cue.point))
            ).first()

            max_num = result[0] if result[0] is not None else 0
            max_point = result[1] if result[1] is not None else 0

            return (max_num, max_point + 10)

    def add_cue(
        self,
        name: str,
        dca_channels: Optional[Dict[int, str]] = None,
        dca_labels: Optional[Dict[int, str]] = None,
        qlab_cue: Optional[str] = None,
        colour: Optional[int] = 0,
        channel_fx: Optional[str] = None,
        fx_mutes: Optional[str] = None,
        snippets: Optional[str] = None,
        number: Optional[int] = None,
        point: Optional[int] = None,
    ) -> int:
        """Add a new cue to the database.

        Args:
            name: Cue name/description
            dca_channels: Dict mapping DCA number (1-12) to channel list string
            dca_labels: Dict mapping DCA number (1-12) to label string
            qlab_cue: QLab cue reference
            colour: Color code (integer)
            channel_fx: Channel FX configuration string
            fx_mutes: FX mute configuration string
            snippets: Snippet configuration string
            number: Cue number (auto-generated if None)
            point: Cue point (auto-generated if None)

        Returns:
            The cue point that was inserted
        """
        if number is None or point is None:
            auto_num, auto_point = self.get_next_cue_number()
            if number is None:
                number = auto_num
            if point is None:
                point = auto_point

        # Build cue with DCA assignments
        cue_data = {
            "number": number,
            "point": point,
            "name": name,
            "colour": colour,
            "qLabCue": qlab_cue,
            "channelFX": channel_fx,
            "fxMutes": fx_mutes,
            "snippets": snippets,
        }

        # Add DCA channels
        if dca_channels:
            for dca_num, channels in dca_channels.items():
                cue_data[f"dca{dca_num:02d}Channels"] = channels

        # Add DCA labels
        if dca_labels:
            for dca_num, label in dca_labels.items():
                cue_data[f"dca{dca_num:02d}Label"] = label

        cue = Cue(**cue_data)

        with Session(self.engine) as session:
            session.add(cue)
            session.commit()

        return point

    def get_cue(self, point: int) -> Optional[Cue]:
        """Get a cue by its point number.

        Args:
            point: Cue point number

        Returns:
            Cue object or None if not found
        """
        with Session(self.engine) as session:
            statement = select(Cue).where(Cue.point == point)
            return session.exec(statement).first()

    def get_all_cues(self) -> List[Cue]:
        """Get all cues ordered by point.

        Returns:
            List of Cue objects
        """
        with Session(self.engine) as session:
            statement = select(Cue).order_by(Cue.point)
            return list(session.exec(statement))

    def update_cue(self, point: int, **kwargs):
        """Update a cue's fields.

        Args:
            point: Cue point to update
            **kwargs: Field names and values to update
        """
        with Session(self.engine) as session:
            statement = select(Cue).where(Cue.point == point)
            cue = session.exec(statement).first()
            if cue:
                for key, value in kwargs.items():
                    setattr(cue, key, value)
                session.add(cue)
                session.commit()

    def delete_cue(self, point: int):
        """Delete a cue by point number.

        Args:
            point: Cue point to delete
        """
        with Session(self.engine) as session:
            statement = select(Cue).where(Cue.point == point)
            cue = session.exec(statement).first()
            if cue:
                session.delete(cue)
                session.commit()

    def get_profiles(self) -> List[Profile]:
        """Get all channel profiles.

        Returns:
            List of Profile objects
        """
        with Session(self.engine) as session:
            statement = select(Profile).order_by(Profile.channel)
            return list(session.exec(statement))

    def get_profile_by_name(self, name: str) -> Optional[Profile]:
        """Get a profile by character name.

        Args:
            name: Character/profile name

        Returns:
            Profile object or None if not found
        """
        with Session(self.engine) as session:
            statement = select(Profile).where(Profile.name == name)
            return session.exec(statement).first()

    def get_channel_for_character(self, character: str) -> Optional[int]:
        """Get the channel number for a character.

        Args:
            character: Character name

        Returns:
            Channel number or None if not found
        """
        profile = self.get_profile_by_name(character)
        return profile.channel if profile else None

    def get_config(self, param: str) -> Optional[str]:
        """Get a configuration value.

        Args:
            param: Configuration parameter name

        Returns:
            Configuration value or None if not found
        """
        with Session(self.engine) as session:
            config = session.get(Config, param)
            return config.value if config else None

    def set_config(self, param: str, value: str):
        """Set a configuration value.

        Args:
            param: Configuration parameter name
            value: Configuration value
        """
        with Session(self.engine) as session:
            config = session.get(Config, param)
            if config:
                config.value = value
            else:
                config = Config(param=param, value=value)
            session.add(config)
            session.commit()

    def get_all_config(self) -> Dict[str, str]:
        """Get all configuration as a dictionary.

        Returns:
            Dictionary of config parameter -> value
        """
        with Session(self.engine) as session:
            statement = select(Config)
            configs = session.exec(statement)
            return {config.param: config.value for config in configs}
