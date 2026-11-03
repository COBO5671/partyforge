import os
from pathlib import Path

from flask import Flask, jsonify, redirect, send_from_directory, session, url_for
from werkzeug.security import generate_password_hash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.middleware.proxy_fix import ProxyFix

db = SQLAlchemy()


def create_app():
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY", "development-only-change-me"),
        SQLALCHEMY_DATABASE_URI=os.getenv(
            "DATABASE_URL", "sqlite:////data/partyforge.db"
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=8 * 1024 * 1024,
        UPLOAD_FOLDER=os.getenv("UPLOAD_FOLDER", "/data/uploads"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "false").lower()
        == "true",
        APP_NAME=os.getenv("APP_NAME", "PartyForge"),
        HOST_EMAIL=os.getenv("HOST_EMAIL", ""),
        MAIL_FROM=os.getenv("MAIL_FROM", ""),
        SMTP_HOST=os.getenv("SMTP_HOST", ""),
        SMTP_PORT=int(os.getenv("SMTP_PORT", "587")),
        SMTP_USERNAME=os.getenv("SMTP_USERNAME", ""),
        SMTP_PASSWORD=os.getenv("SMTP_PASSWORD", ""),
        SMTP_USE_TLS=os.getenv("SMTP_USE_TLS", "true").lower() == "true",
        VAPID_PRIVATE_KEY=os.getenv("VAPID_PRIVATE_KEY", "/data/vapid_private.pem"),
        VAPID_PUBLIC_KEY=os.getenv("VAPID_PUBLIC_KEY", "/data/vapid_public.txt"),
        VAPID_SUBJECT=os.getenv("VAPID_SUBJECT", "mailto:admin@partyforge.local"),
        REMINDER_POLL_SECONDS=int(os.getenv("REMINDER_POLL_SECONDS", "60")),
        PUBLIC_BASE_URL=os.getenv("PUBLIC_BASE_URL", ""),
    )
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)

    from .auth import bp as auth_bp
    from .admin import bp as admin_bp
    from .public import bp as public_bp
    from .security import csrf_token, description_html, description_content, verify_csrf

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(public_bp)
    app.jinja_env.filters["description_html"] = description_html
    app.jinja_env.filters["description_content"] = description_content

    # A content version changes URLs after deployment, even behind browser caches.
    import hashlib
    asset_versions = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()[:12]
        for path in Path(app.static_folder).iterdir() if path.is_file()
    }

    @app.url_defaults
    def version_static_assets(endpoint, values):
        if endpoint == "static" and values.get("filename") in asset_versions:
            values["v"] = asset_versions[values["filename"]]

    @app.before_request
    def csrf_guard():
        return verify_csrf()

    @app.context_processor
    def shared_context():
        unread_notifications = 0
        current_host = None
        if session.get("is_admin"):
            from .models import HostUser, Notification, NotificationRead

            current_host = db.session.get(HostUser, session.get("host_user_id"))
            if current_host:
                event_ids = [link.event_id for link in current_host.event_links]
                read_ids = [
                    row.notification_id
                    for row in NotificationRead.query.filter_by(host_user_id=current_host.id).all()
                ]
                unread_notifications = Notification.query.filter(
                    Notification.event_id.in_(event_ids), ~Notification.id.in_(read_ids)
                ).count()
        return {
            "csrf_token": csrf_token,
            "app_name": app.config["APP_NAME"],
            "unread_notifications": unread_notifications,
            "current_host": current_host,
        }

    @app.get("/uploads/<path:filename>")
    def uploaded_file(filename):
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    @app.get("/sw.js")
    def service_worker():
        response = send_from_directory(app.static_folder, "sw.js")
        response.headers["Service-Worker-Allowed"] = "/"
        response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/manifest.webmanifest")
    def manifest():
        return jsonify(
            name=app.config["APP_NAME"],
            short_name=app.config["APP_NAME"],
            display="standalone",
            background_color="#f6f6f0",
            theme_color="#6d45ff",
            icons=[{"src": "/static/icon.svg", "sizes": "any", "type": "image/svg+xml"}],
        )

    @app.get("/")
    def index():
        if session.get("is_admin"):
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("auth.login"))

    with app.app_context():
        from . import models
        from .models import Event, EventHost, HostUser
        from .push import ensure_vapid_keys

        db.create_all()
        owner = HostUser.query.filter_by(is_owner=True).first()
        if not owner:
            owner = HostUser(
                name=os.getenv("ADMIN_NAME", "Cody"),
                username=os.getenv("ADMIN_USERNAME", "cody").strip().lower() or "cody",
                email=os.getenv("ADMIN_EMAIL", app.config.get("HOST_EMAIL", "")),
                password_hash=generate_password_hash(os.getenv("ADMIN_PASSWORD", "changeme")),
                is_owner=True,
            )
            db.session.add(owner)
            db.session.flush()
        linked_ids = {row.event_id for row in EventHost.query.all()}
        for event in Event.query.all():
            if event.id not in linked_ids:
                db.session.add(EventHost(event=event, user=owner, role="owner"))
        db.session.commit()
        ensure_vapid_keys()

    if app.config["SQLALCHEMY_DATABASE_URI"] != "sqlite:///:memory:":
        from .scheduler import start_reminder_scheduler

        start_reminder_scheduler(app)

    return app
