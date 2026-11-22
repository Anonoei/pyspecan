"""File reader"""
import argparse
import pathlib

from pysdrlib import File as _File
from pysdrlib import Formats as _Formats
from pysdrlib import err as _err

from ...obj import Frequency
from .sink import Sink, SinkConfig

# IQ formats only: real formats would yield real samples
FORMATS = [f.name for f in _Formats if f.is_complex]
DEFAULT_FORMAT = "cf32" # two float32 a sample (a GNU Radio .cfile): what a file whose name says nothing is taken to be

def format_name(fmt: str) -> str:
    """A format's name in `FORMATS`, from it or one of pysdrlib's other spellings ("ci16" for "ci16t")"""
    try:
        name = _Formats[fmt].name
    except KeyError:
        name = None
    if name not in FORMATS:
        raise ValueError(f"unknown format {fmt!r}: one of {', '.join(FORMATS)}")
    return name

def _format_arg(fmt: str) -> str:
    try:
        return format_name(fmt)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from None

def args_file(sink):
    sink.add_argument("-f", "--path", default=None, help="file path")
    sink.add_argument("-F", "--fmt", type=_format_arg, metavar="{" + ",".join(FORMATS) + "}", default=None,
                      help=f"data format (default: a SigMF recording's, else the one the extension names, .cfile .cs16 .cu8..., else {DEFAULT_FORMAT})")

class SinkFile(Sink):
    SEEKABLE = True
    __slots__ = (
        "dev", "fmt", "given", "note",
    )
    def __init__(self, model, **kwargs):
        super().__init__(model, **kwargs)
        fmt = kwargs.get("fmt", None)
        self.fmt = None if fmt is None else format_name(fmt) # the format asked for, None: each file's own (SigMF, extension)
        # rate and frequency given at launch hold for the file given with them, over what its SigMF metadata says
        self.given = {"Fs": int(self._Fs.raw) != int(SinkConfig.Fs), "cf": int(self._cf.raw) != int(SinkConfig.cf)}
        self.note = "" # what was assumed about the file, for the views to say
        self.dev = _File(fmt=self.fmt or DEFAULT_FORMAT)
        self.set_path(kwargs.get("path", None))
        self.given = {"Fs": False, "cf": False} # a file opened later brings its own

    def show(self, ind=0):
        print(" "*ind + f"{self.percent():06.2f}% [{self.dev.fmt.name}] {self.dev.path}")
        print(" "*ind + f"{self.dev.cur_samp}/{self.dev.max_samp}")

    def ready(self):
        return self.get_path() is not None

    def get_path(self):
        return self.dev.get_path()
    def set_path(self, path):
        if path is None or path == "":
            return
        path = pathlib.Path(path)
        old = self.dev
        try:
            dev = _File(path, self.fmt) # without a format: the recording's, or the one its extension names
            self.note = ""
        except FileNotFoundError: # x.sigmf finds x.sigmf-data, anything else has to be there
            return
        except ValueError: # neither says
            dev = _File(path, DEFAULT_FORMAT)
            self.note = f"{path.name}: read as {DEFAULT_FORMAT}, its name does not say its format (choose one with -F / fmt)"
            self.log.warning(self.note)
            print(self.note, flush=True)
        if old.f is not None:
            old.close()
        self.dev = dev
        if dev.rate and not self.given["Fs"]:
            self._Fs = self._valid_fs(Frequency.get(dev.rate))
        if dev.freq is not None and not self.given["cf"]:
            self._cf = Frequency.get(dev.freq)
        self.reset()

    def get_fmt(self):
        return self.dev.get_fmt()
    def set_fmt(self, fmt):
        fmt = format_name(fmt)
        self.fmt = fmt # chosen: it holds for files opened later too
        self.dev.set_fmt(fmt)
        self.note = ""

    def _set_fs(self, fs):
        return fs
    def _set_cf(self, cf):
        return cf

    def reset(self):
        self.dev.reset()

    def next(self, count: int):
        at = self.dev.cur_samp
        try:
            self._samples = self.dev.next(count) # opens the file on the first read
        except _err.Overflow: # the end
            return False
        self._placed(at)
        return True

    def prev(self, count: int):
        try:
            self._samples = self.dev.prev(count)
        except _err.Overflow: # the start
            return False
        self._placed(self.dev.cur_samp)
        return True

    def _placed(self, at: int):
        """The block starts at sample `at`: its time is a SigMF recording's start plus that, else seconds into the file"""
        self.block_index = at
        start = self.dev.meta.start_time if self.dev.meta is not None else None
        self.block_time = (start or 0.0) + at / self.get_fs().raw

    def seek(self, samp: int):
        """Jump to sample `samp`"""
        self.dev.seek(max(0, min(int(samp), self.max_samp)))

    def forward(self, count: int):
        return self.dev.forward(count)

    def reverse(self, count: int):
        return self.dev.reverse(count)

    def percent(self):
        return self.dev.percent()

    def cur_time(self):
        return self.dev.cur_samp/self.get_fs().raw
    def tot_time(self):
        return self.dev.max_samp/self.get_fs().raw
    def skip_time(self, s):
        self.seek(self.dev.cur_samp + int(self.get_fs().raw * s))

    @property
    def cur_samp(self):
        return self.dev.cur_samp

    @property
    def max_samp(self):
        return self.dev.max_samp

    def close(self):
        if self.dev.f is not None:
            self.dev.close()
