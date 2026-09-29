"""Shared request guards for authenticated Flask views."""

from functools import wraps

from flask import abort, g, redirect, url_for

from models.user import STATUS_APPROVED


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.current_user is None or g.current_user.status != STATUS_APPROVED:
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.current_user is None or g.current_user.status != STATUS_APPROVED:
            return redirect(url_for("auth.login"))
        if not g.current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped
