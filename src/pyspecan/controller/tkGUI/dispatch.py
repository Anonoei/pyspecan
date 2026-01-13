import queue
import threading
import time
from enum import Enum, auto

from ... import logger
from ...config import config, Mode
from ...utils.monitor import Memory

class CMD(Enum):
    NEXT = auto()
    PREV = auto()

    START = auto()
    STOP = auto()
    RESET = auto()

    PLOT = auto()

    UPDATE_F = auto()
    UPDATE_NFFT = auto()
    UPDATE_FS = auto()

    UPDATE_MODE = auto()
    UPDATE_SINK = auto()

class STATE(Enum):
    WAITING = auto()
    RUNNING = auto()

class Dispatch:
    def __init__(self, controller):
        self.log = logger.new("tkGUI.dispatch")
        self.ctrl = controller
        self.queue = queue.Queue()

        self.state = STATE.WAITING
        self.running = True
        self.thread = threading.Thread(target=self._run, name="dispatcher")

        self._last_f = self._get_f()

    def start(self):
        self.running = True
        self.thread.start()

    def stop(self):
        self.send(CMD.STOP)
        self.running = False
        self.thread.join(timeout=1)

    def send(self, cmd: CMD, val=None):
        self.queue.put((cmd, val))

    def _run(self):
        while self.running:
            if self.state is not STATE.RUNNING:
                if self.queue.qsize() == 0:
                    time.sleep(0.2)
                    continue
            else:
                self._loop()
            if not self.queue.qsize() == 0:
                cmd, val = self.queue.get()
                if cmd is CMD.NEXT:
                    self.log.trace("executing CMD.NEXT")
                    if self.state is STATE.RUNNING:
                        self.send(CMD.STOP)
                    self._next()
                elif cmd is CMD.PREV:
                    self.log.trace("executing CMD.PREV")
                    if self.state is STATE.RUNNING:
                        self.send(CMD.STOP)
                    self._prev()
                elif cmd is CMD.START:
                    self.log.trace("executing CMD.START")
                    self.state = STATE.RUNNING
                elif cmd is CMD.STOP:
                    self.log.trace("executing CMD.STOP")
                    self.state = STATE.WAITING
                elif cmd is CMD.PLOT:
                    self.log.trace("executing CMD.PLOT")
                    pass
                elif cmd is CMD.RESET:
                    self.log.trace("executing CMD.RESET")
                    if self.state is STATE.RUNNING:
                        self.state = STATE.WAITING
                    self.ctrl.mode.panel.on_reset()
                    self.ctrl.model.reset()
                    self.ctrl.draw_tb()
                elif cmd is CMD.UPDATE_F:
                    self.log.trace("executing CMD.UPDATE_F")
                    self._last_f = None
                    self._update_f()
                elif cmd is CMD.UPDATE_NFFT:
                    self.log.trace("executing CMD.UPDATE_NFFT")
                    self.ctrl.mode.panel.on_update_nfft(self.ctrl.model.get_nfft())
                elif cmd is CMD.UPDATE_FS:
                    self.log.trace("executing CMD.UPDATE_FS")
                    self.ctrl.mode.panel.on_update_fs(self.ctrl.model.get_fs())

    def on_plot(self):
        ptime = time.perf_counter()
        # self._update_f()
        self.ctrl.mode.panel.on_plot(self.ctrl.model)

        ptime = (time.perf_counter() - ptime)
        self.ctrl.view.tb_var_draw_time.set(f"{ptime:06.3f}s")
        self.ctrl.draw_tb()

        # print(f"Plotted in {ptime*1000:.1f}ms / {self.time_show}")
        return ptime

    def _loop(self):
        time_show = self.ctrl.time_show/1000 # convert ms to s
        valid, ptime = self._next()
        if not valid or ptime is None:
            self.send(CMD.STOP)
            return
        wait = time_show-ptime
        if wait > 0:
            self.ctrl.view.tb_lbl_msg.configure(text="")
            time.sleep(wait)
        else:
            if not self.ctrl.model.mode.get_sweep_time() == 0.0:
                if config.MODE == Mode.SWEPT:
                    self.ctrl.model.skip_time(-wait)
                self.ctrl.view.tb_lbl_msg.configure(text="OVERFLOW")

    def _prev(self): # fails on Sink.LIVE
        valid = self.ctrl.model.sink.prev(self.ctrl.model.mode.get_block_size())
        tplot = None
        if valid:
            tplot = self.on_plot()
        return (valid, tplot)

    def _next(self):
        valid = self.ctrl.model.sink.next(self.ctrl.model.mode.get_block_size())
        tplot = None
        if valid:
            tplot = self.on_plot()
        return (valid, tplot)

    def _get_f(self):
        return (self.ctrl.model.f[0], self.ctrl.model.f[-1]+(self.ctrl.model.f[-1]-self.ctrl.model.f[-2]), len(self.ctrl.model.f))
    def _update_f(self):
        if self._last_f is None:
            self._last_f = self._get_f()
            self.ctrl.mode.panel.on_update_f(self._last_f)
        elif not self.ctrl.model.f[0] == self._last_f[0] and not len(self.ctrl.model.f) == self._last_f[2]:
            self._last_f = self._get_f()
            self.ctrl.mode.panel.on_update_f(self._last_f)

    @property
    def last_f(self):
        return self._last_f
