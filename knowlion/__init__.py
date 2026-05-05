__all__ = ["KnowLion"]


def __getattr__(name):
    if name == "KnowLion":
        from .abution_knowlion_driver import KnowLion

        return KnowLion
    raise AttributeError(f"module 'knowlion' has no attribute {name!r}")
