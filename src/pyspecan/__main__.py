"""pyspecan

This file enables using `python3 -m pyspecan`

This makes specan available, by using _internal.main
Use `python3 -m pyspecan --help` to see available arguments
"""
import sys
import pathlib

if __name__ == "__main__":
    try:
        from pyspecan._internal.main import main as _main
    except ImportError: # Makes import work when running src/pyspecan without it installed
        sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
        from pyspecan._internal.main import main as _main
    sys.exit(_main())
