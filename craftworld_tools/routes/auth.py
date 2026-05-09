"""Authentication routes for Craft World Tools.

This module is ready to be wired into app.py with:

    from craftworld_tools.routes.auth import register_auth_routes
    register_auth_routes(app, has_uid_flag)

The old inline routes in app.py should be removed at the same time to avoid
registering duplicate /login, /register, and /logout URLs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from flask import redirect, render_template, request, session, url_for
from jinja2 import ChoiceLoader, FileSystemLoader

from craftworld_tools.services.users import authenticate_user, create_user


HasUidFlag = Callable[[], bool]


def _ensure_package_template_loader(app: Any) -> None:
    """Let a legacy root Flask app find templates in craftworld_tools/templates."""
    package_templates = Path(__file__).resolve().parents[1] / "templates"
    package_loader = FileSystemLoader(str(package_templates))
    current_loader = app.jinja_loader

    if isinstance(current_loader, ChoiceLoader):
        loaders = list(current_loader.loaders)
        for loader in loaders:
            if isinstance(loader, FileSystemLoader) and str(package_templates) in loader.searchpath:
                return
        app.jinja_loader = ChoiceLoader([package_loader, *loaders])
    elif current_loader is not None:
        app.jinja_loader = ChoiceLoader([package_loader, current_loader])
    else:
        app.jinja_loader = package_loader


def _login_user(user: dict[str, Any]) -> None:
    session["user_id"] = int(user["id"])
    session["username"] = user["username"]


def register_auth_routes(app: Any, has_uid_flag: HasUidFlag) -> None:
    """Register login/register/logout routes on the provided Flask app."""
    _ensure_package_template_loader(app)

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
