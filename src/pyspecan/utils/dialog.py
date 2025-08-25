"""tkinter dialogs"""
import pathlib

from tkinter import filedialog

def get_file(strict=True, title: str="", filetypes=None):
    """Prompts for file selection"""
    while True:
        if filetypes is None:
            file = filedialog.askopenfilename(title=title)
        else:
            file = filedialog.askopenfilename(title=title, filetypes=filetypes)
        file = pathlib.Path(file)
        if strict:
            if file.exists():
                return file
        else:
            if file == "":
                return None
            return file
