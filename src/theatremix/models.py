"""SQLModel models for TheatreMix cue database schema."""

from sqlmodel import Field, SQLModel


class Config(SQLModel, table=True):
    """Configuration key-value store."""

    param: str = Field(primary_key=True)
    value: str | None = None


class Cue(SQLModel, table=True):
    """Main cue table with DCA assignments and metadata.

    Note: The actual SQLite table has no PRIMARY KEY constraint, but SQLModel
    requires one for ORM operations. We use (number, point) as a composite key.
    """

    __tablename__ = "cues"

    number: int = Field(default=999, primary_key=True)
    point: int = Field(default=0, primary_key=True)
    name: str | None = None

    # DCA channel assignments (comma-separated channel numbers)
    dca01Channels: str | None = None
    dca02Channels: str | None = None
    dca03Channels: str | None = None
    dca04Channels: str | None = None
    dca05Channels: str | None = None
    dca06Channels: str | None = None
    dca07Channels: str | None = None
    dca08Channels: str | None = None
    dca09Channels: str | None = None
    dca10Channels: str | None = None
    dca11Channels: str | None = None
    dca12Channels: str | None = None

    # DCA labels
    dca01Label: str | None = None
    dca02Label: str | None = None
    dca03Label: str | None = None
    dca04Label: str | None = None
    dca05Label: str | None = None
    dca06Label: str | None = None
    dca07Label: str | None = None
    dca08Label: str | None = None
    dca09Label: str | None = None
    dca10Label: str | None = None
    dca11Label: str | None = None
    dca12Label: str | None = None

    # Additional configuration
    channelPositions: str | None = None
    channelProfiles: str | None = None
    fxMutes: str | None = None
    channelFX: str | None = None
    snippets: str | None = None
    qLabCue: str | None = None
    channelLevels: str | None = None
    scenes: str | None = None
    colour: int | None = None
    scenePoints: str | None = None

    # DCA 9-12 (added to match actual schema)
    dca09Channels: str | None = None
    dca09Label: str | None = None
    dca10Channels: str | None = None
    dca10Label: str | None = None
    dca11Channels: str | None = None
    dca11Label: str | None = None
    dca12Channels: str | None = None
    dca12Label: str | None = None


class Profile(SQLModel, table=True):
    """Channel profiles for characters/actors."""

    __tablename__ = "profiles"

    id: int | None = Field(default=None, primary_key=True)
    channel: int | None = None
    name: str | None = None
    label: str | None = None
    default: int = Field(default=1, sa_column_kwargs={"name": "default"})
    data: str | None = None


class Position(SQLModel, table=True):
    """Stage positions with acoustic properties."""

    __tablename__ = "positions"

    id: int | None = Field(default=None, primary_key=True)
    name: str | None = None
    shortName: str | None = None
    delay: float | None = None
    pan: float | None = None
    buses: str | None = None


class Ensemble(SQLModel, table=True):
    """Ensemble/group definitions with channel assignments."""

    __tablename__ = "ensembles"

    id: int | None = Field(default=None, primary_key=True)
    name: str | None = None
    channels: str | None = None
    channelProfiles: str | None = None


class Actor(SQLModel, table=True):
    """Actor/performer definitions."""

    __tablename__ = "actors"

    id: int | None = Field(default=None, primary_key=True)
    channel: int | None = None
    name: str | None = None
    order: int = Field(default=0, sa_column_kwargs={"name": "order"})
    active: int = Field(default=0)


class ActorProfile(SQLModel, table=True):
    """Actor-to-profile associations.

    Note: The actual SQLite table has no PRIMARY KEY constraint, but SQLModel
    requires one for ORM operations. We use (actor, profile) as a composite key.
    """

    __tablename__ = "actorProfiles"

    actor: int | None = Field(default=None, primary_key=True)
    profile: int | None = Field(default=None, primary_key=True)
    data: str | None = None


class ActorGroup(SQLModel, table=True):
    """Actor group definitions."""

    __tablename__ = "actorGroups"

    id: int | None = Field(default=None, primary_key=True)
    name: str | None = None
    data: str | None = None


class SnippetCache(SQLModel, table=True):
    """Cache for mixer snippets."""

    __tablename__ = "snippetCache"

    snippet: int = Field(primary_key=True)
    name: str | None = None


class FXCache(SQLModel, table=True):
    """Cache for effects."""

    __tablename__ = "fxCache"

    fx: int = Field(primary_key=True)
    name: str | None = None


class SceneCache(SQLModel, table=True):
    """Cache for mixer scenes."""

    __tablename__ = "sceneCache"

    scene: int = Field(primary_key=True)
    point: int = Field(default=0)
    name: str | None = None
