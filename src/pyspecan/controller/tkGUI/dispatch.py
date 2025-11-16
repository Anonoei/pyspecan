import queue
import threading
import time
from enum import Enum, auto

from ...config import config, Mode
from ...utils.monitor import Memory

class CMD(Enum):
    NEXT = auto()
    PREV = auto()

    START = auto()
    STOP = auto()

    PLOT = auto()
    RESET = auto()

    UPDATE_F = auto()
    UPDATE_NFFT = auto()
    UPDATE_FS = auto()

class STATE(Enum):
    WAITING = auto()
    RUNNING = auto()


class Dispatch:
    def __init__(self, controller):
        self.ctrl = controller
        self.queue = queue.Queue()

        self.state = STATE.WAITING
        self.running = True
        self.thread = threading.Thread(target=self._run, name="dispatcher")

        self._last_f = None

    def start(self):
        self.running = True
        self.thread.start()

    def stop(self):
        self.queue.put(CMD.STOP)
        self.running = False
        self.thread.join(timeout=1)

    def _run(self):
        while self.running:
            if self.state is not STATE.RUNNING:
                if self.queue.qsize() == 0:
                    time.sleep(0.2)
                    continue
            else:
                self._loop()
            if not self.queue.qsize() == 0:
                cmd = self.queue.get()
                if cmd is CMD.NEXT:
                    if self.state is STATE.RUNNING:
                        self.queue.put(CMD.STOP)
                    self._next()
                elif cmd is CMD.PREV:
                    if self.state is STATE.RUNNING:
                        self.queue.put(CMD.STOP)
                    self._prev()
                elif cmd is CMD.START:
                    self.state = STATE.RUNNING
                elif cmd is CMD.STOP:
                    self.state = STATE.WAITING
                elif cmd is CMD.PLOT:
                    pass
                elif cmd is CMD.RESET:
                    if self.state is STATE.RUNNING:
                        self.state = STATE.WAITING
                    self.ctrl.panel.on_reset()
                    self.ctrl.model.reset()
                    self.ctrl.draw_tb()
                elif cmd is CMD.UPDATE_F:
                    self._update_f()
                elif cmd is CMD.UPDATE_NFFT:
                    self.ctrl.panel.on_update_nfft(self.ctrl.model.nfft)
                elif cmd is CMD.UPDATE_FS:
                    self.ctrl.panel.on_update_fs(self.ctrl.model.Fs)

    def on_plot(self):
        ptime = time.perf_counter()
        self._update_f()
        self.ctrl.panel.on_plot(self.ctrl.model)

        ptime = (time.perf_counter() - ptime)
        self.ctrl.view.var_draw_time.set(f"{ptime:06.3f}s")
        self.ctrl.draw_tb()

        # print(f"Plotted in {ptime*1000:.1f}ms / {self.time_show}")
        return ptime

    def _loop(self):
        time_show = self.ctrl.time_show/1000 # convert ms to s
        valid, ptime = self._next()
        if not valid or ptime is None:
            self.queue.put(CMD.STOP)
            return
        wait = time_show-ptime
        if wait > 0:
            self.ctrl.view.lbl_msg.configure(text="")
            time.sleep(wait)
        else:
            if not self.ctrl.model.sweep_time == 0.0:
                if config.MODE == Mode.SWEPT:
                    self.ctrl.model.skip_time(-wait)
                self.ctrl.view.lbl_msg.configure(text="OVERFLOW")

    def _prev(self):
        valid = self.ctrl.model.prev()
        tplot = None
        if valid:
            tplot = self.on_plot()
        return (valid, tplot)

    def _next(self):
        valid = self.ctrl.model.next()
        tplot = None
        if valid:
            tplot = self.on_plot()
        return (valid, tplot)

    def _update_f(self):
        def __check():
            return (self.ctrl.model.f[0], self.ctrl.model.f[-1]+(self.ctrl.model.f[-1]-self.ctrl.model.f[-2]), len(self.ctrl.model.f))
        if self._last_f is None:
            self._last_f = __check()
        elif not self.ctrl.model.f[0] == self._last_f[0] and not len(self.ctrl.model.f) == self._last_f[2]:
            self._last_f = __check()
        self.ctrl.panel.on_update_f(self._last_f)
