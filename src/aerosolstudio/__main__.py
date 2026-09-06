"""Module execution support for ``python -m aerosolstudio``."""

from aerosolstudio.app.launcher import run_app


def main() -> int:
    """Launch the canonical Bokeh application."""

    return run_app()


if __name__ == "__main__":
    raise SystemExit(main())
