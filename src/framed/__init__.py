"""framed: a scene server for the Divoom Pixoo-64."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("framed")
except PackageNotFoundError:
    __version__ = "0.0.0"
