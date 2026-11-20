"""tkinter dialogs"""
import pathlib
from tkinter import filedialog


def save_file(title: str = "", filetypes=None, defaultextension: str = ""):
    """Prompts for a file to write, None when cancelled"""
    file = filedialog.asksaveasfilename(title=title, filetypes=filetypes or [], defaultextension=defaultextension)
    if file == "" or file == ():
        return None
    return pathlib.Path(file)

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
