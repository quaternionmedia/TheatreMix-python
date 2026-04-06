"""SQLAlchemy models for TheatreMix cue database schema.

Uses a separate DeclarativeBase with its own MetaData to avoid table name
collisions when co-installed with other SQLModel-based packages (e.g. ShowRunner).
"""

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class TheatreMixBase(DeclarativeBase):
    """Declarative base with isolated MetaData for TheatreMix models."""

    def model_dump(self) -> dict:
        """Serialize all column values to a dictionary."""
        return {c.key: getattr(self, c.key) for c in self.__table__.columns}


class Config(TheatreMixBase):
    """Configuration key-value store."""

    __tablename__ = 'config'

    param: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[str | None] = mapped_column(default=None)


class Cue(TheatreMixBase):
    """Main cue table with DCA assignments and metadata.

    Note: The actual SQLite table has no PRIMARY KEY constraint, but SQLAlchemy
    requires one for ORM operations. We use (number, point) as a composite key.
    """

    __tablename__ = 'cues'

    number: Mapped[int] = mapped_column(primary_key=True, default=999)
    point: Mapped[int] = mapped_column(primary_key=True, default=0)
    name: Mapped[str | None] = mapped_column(default=None)

    # DCA channel assignments (comma-separated channel numbers)
    dca01Channels: Mapped[str | None] = mapped_column(default=None)
    dca02Channels: Mapped[str | None] = mapped_column(default=None)
    dca03Channels: Mapped[str | None] = mapped_column(default=None)
    dca04Channels: Mapped[str | None] = mapped_column(default=None)
    dca05Channels: Mapped[str | None] = mapped_column(default=None)
    dca06Channels: Mapped[str | None] = mapped_column(default=None)
    dca07Channels: Mapped[str | None] = mapped_column(default=None)
    dca08Channels: Mapped[str | None] = mapped_column(default=None)
    dca09Channels: Mapped[str | None] = mapped_column(default=None)
    dca10Channels: Mapped[str | None] = mapped_column(default=None)
    dca11Channels: Mapped[str | None] = mapped_column(default=None)
    dca12Channels: Mapped[str | None] = mapped_column(default=None)

    # DCA labels
    dca01Label: Mapped[str | None] = mapped_column(default=None)
    dca02Label: Mapped[str | None] = mapped_column(default=None)
    dca03Label: Mapped[str | None] = mapped_column(default=None)
    dca04Label: Mapped[str | None] = mapped_column(default=None)
    dca05Label: Mapped[str | None] = mapped_column(default=None)
    dca06Label: Mapped[str | None] = mapped_column(default=None)
    dca07Label: Mapped[str | None] = mapped_column(default=None)
    dca08Label: Mapped[str | None] = mapped_column(default=None)
    dca09Label: Mapped[str | None] = mapped_column(default=None)
    dca10Label: Mapped[str | None] = mapped_column(default=None)
    dca11Label: Mapped[str | None] = mapped_column(default=None)
    dca12Label: Mapped[str | None] = mapped_column(default=None)

    # Additional configuration
    channelPositions: Mapped[str | None] = mapped_column(default=None)
    channelProfiles: Mapped[str | None] = mapped_column(default=None)
    fxMutes: Mapped[str | None] = mapped_column(default=None)
    channelFX: Mapped[str | None] = mapped_column(default=None)
    snippets: Mapped[str | None] = mapped_column(default=None)
    qLabCue: Mapped[str | None] = mapped_column(default=None)
    channelLevels: Mapped[str | None] = mapped_column(default=None)
    scenes: Mapped[str | None] = mapped_column(default=None)
    colour: Mapped[int | None] = mapped_column(default=None)
    scenePoints: Mapped[str | None] = mapped_column(default=None)


class Profile(TheatreMixBase):
    """Channel profiles for characters/actors."""

    __tablename__ = 'profiles'

    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[int | None] = mapped_column(default=None)
    name: Mapped[str | None] = mapped_column(default=None)
    label: Mapped[str | None] = mapped_column(default=None)
    default: Mapped[int] = mapped_column(default=1)
    data: Mapped[str | None] = mapped_column(default=None)


class Position(TheatreMixBase):
    """Stage positions with acoustic properties."""

    __tablename__ = 'positions'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(default=None)
    shortName: Mapped[str | None] = mapped_column(default=None)
    delay: Mapped[float | None] = mapped_column(default=None)
    pan: Mapped[float | None] = mapped_column(default=None)
    buses: Mapped[str | None] = mapped_column(default=None)


class Ensemble(TheatreMixBase):
    """Ensemble/group definitions with channel assignments."""

    __tablename__ = 'ensembles'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(default=None)
    channels: Mapped[str | None] = mapped_column(default=None)
    channelProfiles: Mapped[str | None] = mapped_column(default=None)


class Actor(TheatreMixBase):
    """Actor/performer definitions."""

    __tablename__ = 'actors'

    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[int | None] = mapped_column(default=None)
    name: Mapped[str | None] = mapped_column(default=None)
    order: Mapped[int] = mapped_column(default=0)
    active: Mapped[int] = mapped_column(default=0)


class ActorProfile(TheatreMixBase):
    """Actor-to-profile associations.

    Note: The actual SQLite table has no PRIMARY KEY constraint, but SQLAlchemy
    requires one for ORM operations. We use (actor, profile) as a composite key.
    """

    __tablename__ = 'actorProfiles'

    actor: Mapped[int] = mapped_column(primary_key=True)
    profile: Mapped[int] = mapped_column(primary_key=True)
    data: Mapped[str | None] = mapped_column(default=None)


class ActorGroup(TheatreMixBase):
    """Actor group definitions."""

    __tablename__ = 'actorGroups'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(default=None)
    data: Mapped[str | None] = mapped_column(default=None)


class SnippetCache(TheatreMixBase):
    """Cache for mixer snippets."""

    __tablename__ = 'snippetCache'

    snippet: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(default=None)


class FXCache(TheatreMixBase):
    """Cache for effects."""

    __tablename__ = 'fxCache'

    fx: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(default=None)


class SceneCache(TheatreMixBase):
    """Cache for mixer scenes."""

    __tablename__ = 'sceneCache'

    scene: Mapped[int] = mapped_column(primary_key=True)
    point: Mapped[int] = mapped_column(default=0)
    name: Mapped[str | None] = mapped_column(default=None)
