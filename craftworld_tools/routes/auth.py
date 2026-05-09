"""Authentication routes for Craft World Tools.

This module is ready to be wired into app.py with:

    from craftworld_tools.routes.auth import register_auth_routes
    register_auth_routes(app, has_uid_flag)

The old inline routes in app.py should be removed at the same time to avoid
registering duplicate /login, /register, and /logout URLs.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from flask import redirect, render_template, request, session, url_for

from craftworld_tools.services.users import authenticate_user, create_user


HasUidFlag = Callable[[], bool]


def _login_user(user: dict[str, Any]) -> None:
    session["user_id"] = int(user["id"])
    session["username"] = user["username"]


def register_auth_routes(app: Any, has_uid_flag: HasUidFlag) -> None:
    """Register login/register/logout routes on the provided Flask app."""

    @app.route("/register", methods=["GET", "POST"])
    def register():
        error: Optional[str] = None
        if request.method == "POST":
            username = (request.form.get("username") or "").strip()
            password = (request.form.get("password") or "").strip()
            confirm = (request.form.get("confirm") or "").strip()

            if not username or not password:
                error = "Username and password are required."
            elif password != confirm:
                error = "Passwords do not match."
            else:
                try:
                    user = create_user(username, password)
                    _login_user(user)
                    return redirect(url_for("boosts"))
                except ValueError as exc:
                    error = str(exc)

        return render_template("auth/register.html", error=error, has_uid=has_uid_flag(), title="Create Account")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        error: Optional[str] = None
        if request.method == "POST":
            username = (request.form.get("username") or "").strip()
            password = (request.form.get("password") or "").strip()

            if not username or not password:
                error = "Username and password are required."
            else:
                user = authenticate_user(username, password)
                if user is None:
                    error = "Invalid username or password."
                else:
                    _login_user(user)
                    return redirect(url_for("boosts"))

        return render_template("auth/login.html", error=error, has_uid=has_uid_flag(), title="Log In")

    @app.route("/logout")
    def logout():
        session.pop("user_id", None)
        session.pop("username", None)
        return redirect(url_for("index"))
