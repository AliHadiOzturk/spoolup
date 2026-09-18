__all__ = ["main"]


def __getattr__(name):
    # Lazy export so lightweight subpackages (e.g. spoolup.dashboard) can be
    # imported without pulling in the runtime's third-party dependencies.
    if name == "main":
        from spoolup.main import main

        return main
    raise AttributeError("module %r has no attribute %r" % (__name__, name))
