# SPDX-License-Identifier: MIT
"""Progress messages shared by the desktop and terminal front ends."""
import time


class Reporter:
    def __init__(self, callback=None):
        self.callback = callback or self.console
        self.started = time.monotonic()

    @staticmethod
    def console(event):
        suffix = ''
        if event.get('total'):
            suffix = ' (%d/%d bytes)' % (event['current'], event['total'])
        print(event['message'] + suffix, flush=True)

    def emit(self, stage, message, **values):
        self.callback(dict(stage=stage, message=message,
                           elapsed=int(time.monotonic()-self.started), **values))
