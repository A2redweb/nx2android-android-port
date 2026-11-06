"""Filled in by the GUI server at start-up."""
_before = {}


def set_before(v):
    global _before
    _before = v


def before(): return _before
