from collections import Counter
import linecache
import os
import tracemalloc

import cProfile

from ..config import config

class Memory:
    __instance = None

    def __new__(cls):
        if cls.__instance is None:
            cls.__instance = object.__new__(cls)
            cls._peak = None
            cls._peak_tot = 0
        return cls.__instance

    def __str__(self):
        return f"{tracemalloc.get_traced_memory()}"

    def start(self):
        tracemalloc.start()

    def stop(self):
        tracemalloc.stop()

    def peak(self):
        if self._peak is None:
            _size_1, self._peak = tracemalloc.get_traced_memory()
            tracemalloc.reset_peak()
            self._peak_tot = self._peak_tot if self._peak < self._peak_tot else self._peak
        else:
            _size_2, peak_2 = tracemalloc.get_traced_memory()
            tracemalloc.reset_peak()
            print(f"Peak 1 {self._peak}, 2: {peak_2}, tot {self._peak_tot}")
            self._peak_tot = self._peak_tot if peak_2 < self._peak_tot else peak_2
            self._peak = None

    def _snapshot(self):
        return tracemalloc.take_snapshot()

    def show(self, snapshot=None, key_type='lineno', limit=3):
        if snapshot is None:
            snapshot = self._snapshot()
        snapshot = snapshot.filter_traces((
            tracemalloc.Filter(False, "<frozen importlib._bootstrap>"),
            tracemalloc.Filter(False, "<frozen importlib._bootstrap_external>"),
            tracemalloc.Filter(False, "<unknown>"),
        ))
        top_stats = snapshot.statistics(key_type, cumulative=True)

        print("Top %s lines" % limit)
        for index, stat in enumerate(top_stats[:limit], 1):
            frame = stat.traceback[0]
            # replace "/path/to/module/file.py" with "module/file.py"
            filename = os.sep.join(frame.filename.split(os.sep)[-2:])
            print("#%s: %s:%s: %.1f KiB"
                % (index, filename, frame.lineno, stat.size / 1024))
            line = linecache.getline(frame.filename, frame.lineno).strip()
            if line:
                print('    %s' % line)

        other = top_stats[limit:]
        if other:
            size = sum(stat.size for stat in other)
            print("%s other: %.1f KiB" % (len(other), size / 1024))
        total = sum(stat.size for stat in top_stats)
        print("Total allocated size: %.1f KiB" % (total / 1024))

class Profile:
    __instance = None

    def __new__(cls):
        if cls.__instance is None:
            cls.__instance = object.__new__(cls)
            cls._pr = cProfile.Profile()
        return cls.__instance

    def enable(self):
        self._pr.enable()

    def disable(self):
        self._pr.disable()

    def show(self, sort=-1):
        self._pr.print_stats(sort)

    def dump(self, path):
        self._pr.dump_stats(path)
