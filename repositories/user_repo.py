from extensions import db
from schemas.user import UserSyllabus as User
from typing import Optional


def get_user_by_id(user_id: int) -> Optional[User]:
	return User.query.filter_by(user_id=user_id).first()


def get_user_by_username(username: str) -> Optional[User]:
	return User.query.filter_by(user_name=username).first()


def get_user_by_email(email: str) -> Optional[User]:
	return User.query.filter_by(email=email).first()


def create_user(username: str, password_hash: str, email: str) -> Optional[User]:
	try:
		u = User(user_name=username, password_hash=password_hash, email=email)
		db.session.add(u)
		db.session.commit()
		return u
	except Exception:
		try:
			db.session.rollback()
		except Exception:
			pass
		return None


def set_password_by_user_id(user_id: int, password_hash: str) -> Optional[User]:
	u = get_user_by_id(user_id)
	if not u:
		return None
	try:
		u.password_hash = password_hash
		db.session.commit()
		return u
	except Exception:
		try:
			db.session.rollback()
		except Exception:
			pass
		return None


def update_user(user_id: int, **kwargs) -> Optional[User]:
	u = get_user_by_id(user_id)
	if not u:
		return None
	allowed = {'user_name', 'email'}
	changed = False
	for k, v in kwargs.items():
		if k in allowed and v is not None:
			setattr(u, k, v)
			changed = True
	if not changed:
		return u
	try:
		db.session.commit()
		return u
	except Exception:
		try:
			db.session.rollback()
		except Exception:
			pass
		return None


def list_all_users_brief():
	rows = User.query.order_by(User.user_id.desc()).all()
	out = []
	for r in rows:
		out.append({'user_id': r.user_id, 'user_name': r.user_name, 'email': r.email, 'create_time': getattr(r, 'create_time', None)})
	return out

