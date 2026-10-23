import importlib.metadata

try:
    __version__ = importlib.metadata("theatremix")
except importlib.metadata.PackageNotFoundError:
    __version__ = 'custom'
