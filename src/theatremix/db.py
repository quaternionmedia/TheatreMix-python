"""SQLModel-based database integration for QLab cue management."""

from typing import Optional, List, Dict, Any
from pathlib import Path
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import Session

from .models import (
    TheatreMixBase,
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


class TheatreMixDB:
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
        TheatreMixBase.metadata.create_all(self.engine)

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
            result = session.execute(
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

    def get_cue(self, number: int, point: int) -> Optional[Cue]:
        """Get a cue by its (number, point) key."""
        with Session(self.engine) as session:
            return session.get(Cue, (number, point))

    def get_dca_numbers(self) -> List[int]:
        """DCA numbers the grid shows, from the ``dcas`` config (e.g. [1..12])."""
        raw = self.get_config('dcas') or ''
        return [int(x) for x in raw.split(',') if x.strip()]

    def replace_cues(self, cues: List[Cue]):
        """Replace every cue in one transaction (used by Generate).

        expire_on_commit=False keeps the cues readable after the write.
        """
        with Session(self.engine, expire_on_commit=False) as session:
            session.execute(delete(Cue))
            session.add_all(cues)
            session.commit()

    def get_all_cues(self) -> List[Cue]:
        """Get all cues ordered by (number, point).

        Returns:
            List of Cue objects
        """
        with Session(self.engine) as session:
            statement = select(Cue).order_by(Cue.number, Cue.point)
            return list(session.execute(statement).scalars())

    def update_cue(self, number: int, point: int, **kwargs):
        """Update fields of the cue at (number, point). Changing number/point renumbers it."""
        with Session(self.engine) as session:
            cue = session.get(Cue, (number, point))
            if cue:
                for key, value in kwargs.items():
                    setattr(cue, key, value)
                session.commit()

    def renumber_cue(self, number: int, point: int, new_number: int, new_point: int):
        """Move a cue to a new (number, point). The table has no PK, so check for a clash first."""
        if (new_number, new_point) != (number, point) and self.get_cue(new_number, new_point):
            raise ValueError(f'Cue {new_number}.{new_point} already exists')
        with Session(self.engine) as session:
            cue = session.get(Cue, (number, point))
            if cue:
                cue.number, cue.point = new_number, new_point
                session.commit()

    def copy_target(self, number: int, point: int) -> tuple[int, int]:
        """Key for a copy of a cue, halfway to the next cue in order.

        Cue numbers are read in hundredths: point 50 is .50, so 5.0 and 6.0 give 5.50.
        Raises ValueError if the cue is missing, has no cue after it, points are outside
        0-99, or no whole hundredth lies between the two cues.
        """
        with Session(self.engine) as session:
            keys = [(c.number, c.point) for c in session.execute(
                select(Cue).order_by(Cue.number, Cue.point)).scalars()]
        if (number, point) not in keys:
            raise ValueError(f'Cue {number}.{point} not found')
        i = keys.index((number, point))
        if i + 1 == len(keys):
            raise ValueError(f'Cue {number}.{point} has no cue after it to copy towards')
        nxt = keys[i + 1]
        if not all(0 <= p < 100 for p in (point, nxt[1])):
            raise ValueError('Points must be 0-99 to place a copy between cues')
        lo, hi = number * 100 + point, nxt[0] * 100 + nxt[1]
        if hi - lo < 2:
            raise ValueError(f'No room between {number}.{point} and {nxt[0]}.{nxt[1]}')
        return divmod((lo + hi) // 2, 100)

    def copy_cue(self, number: int, point: int) -> tuple[int, int]:
        """Duplicate a cue halfway to the next cue (see copy_target). Returns the new (number, point)."""
        new_number, new_point = self.copy_target(number, point)
        with Session(self.engine) as session:
            src = session.get(Cue, (number, point))
            data = {c.key: getattr(src, c.key) for c in Cue.__table__.columns}
            data['number'], data['point'] = new_number, new_point
            session.add(Cue(**data))
            session.commit()
        return new_number, new_point

    def snapshot_cues(self) -> List[dict]:
        """Plain-dict copy of every cue column, for undo."""
        return [{c.key: getattr(cue, c.key) for c in Cue.__table__.columns} for cue in self.get_all_cues()]

    def restore_cues(self, snapshot: List[dict]):
        """Replace the whole cue list with a snapshot from snapshot_cues()."""
        self.replace_cues([Cue(**d) for d in snapshot])

    def delete_cue(self, number: int, point: int):
        """Delete the cue at (number, point)."""
        with Session(self.engine) as session:
            cue = session.get(Cue, (number, point))
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
            return list(session.execute(statement).scalars())

    def get_ensembles(self) -> List[Ensemble]:
        """All ensembles (name + channel list), ordered by name."""
        with Session(self.engine) as session:
            return list(session.execute(select(Ensemble).order_by(Ensemble.name)).scalars())

    def list_rows(self, model) -> list:
        """All rows of a table model (Profile, Ensemble, Actor), ordered by id."""
        with Session(self.engine) as session:
            return list(session.execute(select(model).order_by(model.id)).scalars())

    def add_row(self, model, **fields) -> int:
        with Session(self.engine) as session:
            row = model(**fields)
            session.add(row)
            session.commit()
            return row.id

    def update_row(self, model, row_id: int, **fields):
        with Session(self.engine) as session:
            row = session.get(model, row_id)
            if row:
                for key, value in fields.items():
                    setattr(row, key, value)
                session.commit()

    def add_named_rows(self, model, rows: List[dict], overwrite: bool = False) -> tuple[int, int, int]:
        """Add rows by 'name'. Returns (added, overwritten, skipped).

        A name already in the table is skipped, or with overwrite=True has the row's fields
        set on the existing row (fields absent from the row are kept). A name repeated within
        rows is skipped after its first row, or with overwrite=True applied in order.
        """
        with Session(self.engine) as session:
            by_name = {r.name: r for r in session.execute(select(model)).scalars()}
            added = overwritten = skipped = 0
            for row in rows:
                cur = by_name.get(row['name'])
                if cur is None:
                    cur = model(**row)
                    session.add(cur)
                    by_name[row['name']] = cur
                    added += 1
                elif overwrite:
                    for key, value in row.items():
                        setattr(cur, key, value)
                    overwritten += 1
                else:
                    skipped += 1
            session.commit()
        return added, overwritten, skipped

    def delete_row(self, model, row_id: int):
        with Session(self.engine) as session:
            row = session.get(model, row_id)
            if row:
                session.delete(row)
                session.commit()

    def get_profile_by_name(self, name: str) -> Optional[Profile]:
        """Get a profile by character name.

        Args:
            name: Character/profile name

        Returns:
            Profile object or None if not found
        """
        with Session(self.engine) as session:
            statement = select(Profile).where(Profile.name == name)
            return session.execute(statement).scalars().first()

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
            configs = session.execute(statement).scalars()
            return {config.param: config.value for config in configs}
