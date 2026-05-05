__all__ = ["KnowLion"]


def __getattr__(name):
    if name == "KnowLion":
        from knowlion.abution_knowlion_driver import KnowLion

        return KnowLion
    raise AttributeError(name)
