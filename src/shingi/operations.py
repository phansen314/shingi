"""Operations: the domain layer (see operations.md)."""

from importlib.metadata import version as package_version


def version():
    return {"version": package_version("shingi")}
