"""pyspecan

This file enables using `python3 -m pyspecan`

This makes specan available, by using _internal.main
Use `python3 -m pyspecan --help` to see available arguments
"""
import sys

if __name__ == "__main__":
    from pyspecan._internal.main import main as _main
    sys.exit(_main())
