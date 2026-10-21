"""Synthetic Flask backend for same-origin HTTPS Angular/Flask browser QA.

Run only in isolated GitHub Actions; never start with production credentials or DB.
"""
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask, jsonify
from flask_jwt_extended import JWTManager, get_jwt, jwt_required
from werkzeug.serving import make_server

from app.extensions import db
from app.models.auth_refresh_session import AuthRefreshSessionORM
from app.models.user_model import UserORM
from app.routes.auth_routes import auth_bp
from app.services.auth_refresh_service import is_access_revoked

ORIGIN = "https://127.0.0.1:4443"
USER = SimpleNamespace(
    id=47,
    username="qa_browser",
    rol="ADMINISTRADOR",
    sucursal_id=1000,
    sucursales_ids=[1000],
    department_id=7,
    verify_password=lambda password: password == "synthetic-password",
)


def main():
    with TemporaryDirectory(prefix="suite-auth-qa-") as directory:
        app = Flask(__name__)
        app.config.update(
            TESTING=True,
            SECRET_KEY="synthetic-qa-flask-secret",
            JWT_SECRET_KEY="synthetic-qa-jwt-signature",
            JWT_ACCESS_TOKEN_EXPIRES=timedelta(minutes=2),
            SQLALCHEMY_DATABASE_URI="sqlite:///" + str(Path(directory) / "qa.sqlite"),
            CORS_ORIGINS=[ORIGIN],
            AUTH_REFRESH_ENABLED=True,
            AUTH_REFRESH_IDLE_MINUTES=45,
            AUTH_REFRESH_ABSOLUTE_HOURS=12,
            AUTH_REFRESH_COOKIE_NAME="suite_refresh",
        )
        db.init_app(app)
        jwt_manager = JWTManager(app)
        jwt_manager.token_in_blocklist_loader(is_access_revoked)
        app.register_blueprint(auth_bp, url_prefix="/api/auth")

        @app.get("/api/qa/health")
        def health():
            return jsonify({"status": "ok"})

        @app.get("/api/qa/rotation")
        def rotations():
            rows = AuthRefreshSessionORM.query.all()
            return jsonify({
                "sessions": len(rows),
                "rotations": sum(row.rotation_count for row in rows),
                "revoked": sum(row.revoked_at is not None for row in rows),
            })

        @app.get("/api/qa/whoami")
        @jwt_required()
        def whoami():
            return jsonify({"session_id": get_jwt().get("sid"), "authorized": True})

        @app.route("/api/<path:unused>", methods=["GET", "POST", "PUT", "DELETE"])
        def harmless_qa_stub(unused):
            return jsonify({})

        with app.app_context():
            db.session.execute(
                db.text("CREATE TABLE users (id INTEGER PRIMARY KEY)")
            )
            db.session.execute(
                db.text("INSERT INTO users (id) VALUES (47)")
            )
            db.session.commit()
            AuthRefreshSessionORM.__table__.create(db.engine)

        def by_username(username):
            return USER if username == USER.username else None

        with patch.object(UserORM, "get_by_username", by_username), patch.object(
            UserORM, "get_by_id", lambda user_id: USER if str(user_id) == "47" else None
        ):
            server = make_server("127.0.0.1", 5101, app, threaded=True)
            print("AUTH_LAB_BACKEND_READY", flush=True)
            try:
                server.serve_forever()
            finally:
                server.server_close()


if __name__ == "__main__":
    main()
