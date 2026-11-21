"""PyInstaller entry point (src/build.spec): the views and controllers are imported by name at run time, import them here so they are bundled"""
import pyspecan.controller.cui
import pyspecan.controller.tk_gui
import pyspecan.view.cui
import pyspecan.view.tk_gui  # noqa: F401
from pyspecan._internal.main import main

main()
