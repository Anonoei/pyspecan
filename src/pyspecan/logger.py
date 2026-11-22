"""pyspecan's loggers, all under `pyspecan`. A library user configures logging as for any library; the command line
calls `setup` (--log_level, --log_file) to write them to stderr"""
import logging
import sys
from logging.handlers import RotatingFileHandler

LOG_LEVEL_TRACE = 5
LEVELS = ("trace", "debug", "info", "warning", "error")

logging.addLevelName(LOG_LEVEL_TRACE, "TRACE")

class TraceLogger(logging.Logger):
    def trace(self, msg, *args, **kwargs):
        if self.isEnabledFor(LOG_LEVEL_TRACE):
            self._log(LOG_LEVEL_TRACE, msg, args, **kwargs)

formatter = logging.Formatter("%(asctime)s %(levelname)-7s <%(name)s> %(message)s", datefmt="%H:%M:%S")

def new(name: str) -> TraceLogger:
    """The logger `pyspecan.<name>`, a TraceLogger (has `trace`)"""
    manager = logging.Logger.manager
    full = f"pyspecan.{name}"
    if full not in manager.loggerDict: # make this one a TraceLogger, without changing the class of anyone else's
        before = manager.loggerClass
        manager.setLoggerClass(TraceLogger)
        try:
            log = logging.getLogger(full)
        finally:
            manager.loggerClass = before
    else:
        log = logging.getLogger(full)
    if not isinstance(log, TraceLogger): # made by plain getLogger before: give it trace
        log.__class__ = TraceLogger
    return log # type: ignore[return-value]

def level_of(name: str) -> int:
    return LOG_LEVEL_TRACE if name == "trace" else getattr(logging, name.upper())

_handlers: list[logging.Handler] = []

def setup(level: str = "info", path: str | None = None):
    """Write pyspecan's (and uvicorn's) log to stderr from `level` on, and everything to `path` when given.
    Calling it again replaces what an earlier call set up"""
    targets = [logging.getLogger("pyspecan")] + [logging.getLogger("uvicorn")] # uvicorn.error, .access propagate to it
    for log in targets:
        for h in _handlers:
            log.removeHandler(h)
    for h in _handlers:
        h.close()
    _handlers.clear()

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(level_of(level))
    console.setFormatter(formatter)
    _handlers.append(console)
    if path:
        file = RotatingFileHandler(path, maxBytes=1024*1024, backupCount=3)
        file.setLevel(LOG_LEVEL_TRACE)
        file.setFormatter(formatter)
        _handlers.append(file)
    root = logging.getLogger("pyspecan")
    root.setLevel(LOG_LEVEL_TRACE if path else level_of(level))
    for log in targets:
        for h in _handlers:
            log.addHandler(h)
        if log is not root:
            log.propagate = False # not on to the root logger as well
    return root

def console_level() -> int | None:
    """The level `setup` writes to stderr from, None without `setup` (a library user's own logging)"""
    return _handlers[0].level if _handlers else None
