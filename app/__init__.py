# Version is read from the installed package metadata (single source of truth:
# the root pyproject.toml). Falls back when running from a raw source checkout
# without `pip install -e .`.
try:
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _pkg_version
    try:
        __version__ = _pkg_version("ghostbit")
    except PackageNotFoundError:
        __version__ = "0.0.0+source"
except ImportError:
    __version__ = "0.0.0+source"

