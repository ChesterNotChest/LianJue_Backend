"""Learning profile agent package.

This package holds the small, stable contracts used by
``tasks.learning_profile_task``. The task module still owns the public tool
entry points while the package gives those contracts a home that can grow
without turning the task file into the whole subsystem.
"""

from .models import LearningProfileDeps, LearningProfileResult

__all__ = ["LearningProfileDeps", "LearningProfileResult"]
