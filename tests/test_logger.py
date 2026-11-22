import logging

from pyspecan import logger


def test_loggers_are_under_pyspecan_and_have_trace(caplog):
    log = logger.new("test.thing")
    assert log.name == "pyspecan.test.thing" and isinstance(log, logger.TraceLogger)
    with caplog.at_level(logger.LOG_LEVEL_TRACE, logger="pyspecan"):
        log.trace("fine %d", 1)
        log.info("hello")
    assert [r.getMessage() for r in caplog.records if r.name == "pyspecan.test.thing"] == ["fine 1", "hello"]
    assert logger.new("test.thing") is log

def test_new_leaves_other_loggers_alone():
    logger.new("test.other")
    assert type(logging.getLogger("not.pyspecan.at.all")) is logging.Logger

def test_setup_writes_to_stderr_from_the_level_and_replaces_itself(capsys, tmp_path):
    root = logging.getLogger("pyspecan")
    level, propagate = root.level, logging.getLogger("uvicorn").propagate
    try:
        logger.setup("warning")
        logger.setup("info", str(tmp_path / "x.log")) # again: one console handler, not two
        assert logger.console_level() == logging.INFO
        log = logger.new("test.setup")
        log.info("shown")
        log.debug("in the file only")
        logging.getLogger("uvicorn.error").warning("from uvicorn") # uvicorn.run sets its own levels
        err = capsys.readouterr().err
        assert err.count("shown") == 1 and "in the file only" not in err and "from uvicorn" in err
        for h in logger._handlers:
            h.flush()
        assert "in the file only" in (tmp_path / "x.log").read_text()
    finally:
        for log in (root, logging.getLogger("uvicorn")):
            for h in logger._handlers:
                log.removeHandler(h)
        for h in logger._handlers:
            h.close()
        logger._handlers.clear()
        root.setLevel(level)
        logging.getLogger("uvicorn").propagate = propagate
