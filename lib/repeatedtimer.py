#!/usr/bin/env python3
"""
From: https://stackoverflow.com/a/40965385
Extended to prevent simultaneous runs
"""

import threading
import time


class RepeatedTimer(object):
    def __init__(self, interval, function, *args, **kwargs):
        self._timer = None
        self.interval = interval
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.is_running = False
        self.next_call = time.time()
        # Determine if we should actually run the method again
        # The run function will set this to true after it is finished
        self.run = True
        self.start()

    def _run(self):
        self.is_running = False
        self.start()
        if self.run:
            self.run = False
            self.function(*self.args, **self.kwargs)
            self.run = True

    def start(self):
        if not self.is_running:
            self.next_call += self.interval
            self._timer = threading.Timer(
                self.next_call - time.time(), self._run)
            self._timer.start()
            self.is_running = True

    def stop(self):
        self._timer.cancel()
        self.is_running = False
