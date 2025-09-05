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
        if file == "" or file == ():
            if strict:
                continue
            return None
        file = pathlib.Path(file)
        if not file.exists():
            if strict:
                continue
            return None
        return file
