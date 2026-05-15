"""Learning profile agent package.

This package holds the small, stable contracts used by
``tasks.learning_profile_task``. The task module still owns the public tool
entry points while the package gives those contracts a home that can grow
without turning the task file into the whole subsystem.
"""

from .models import LearningProfileDeps, LearningProfileResult
from .storage import (
	load_json_file,
	build_personal_profile_path,
	get_persisted_learning_profile,
	load_existing_profile,
	merge_profile_update,
	profile_has_required_identity,
	profile_root_dir,
	save_personal_profile,
)

__all__ = [
	"LearningProfileDeps",
	"LearningProfileResult",
	"build_personal_profile_path",
	"get_persisted_learning_profile",
	"load_existing_profile",
	"load_json_file",
	"merge_profile_update",
	"profile_has_required_identity",
	"profile_root_dir",
	"save_personal_profile",
]
