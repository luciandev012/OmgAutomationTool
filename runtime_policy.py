"""Production policy: observe/act/verify immediately; never sleep between steps.

Only cancellation/pause waits, OS command timeouts and inactivity deadlines
may block. Inject a simulated sleeper explicitly in deterministic unit tests.
"""


def no_step_delay(_seconds=0):
    return None
