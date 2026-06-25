# backend/app/models/permissions.py

from app import db


class PermissionModuleORM(db.Model):
    __tablename__ = "permission_modules"

    id = db.Column(db.Integer, primary_key=True)

    key = db.Column(db.String(120), nullable=False)
    name = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=True)

    is_active = db.Column(db.Boolean, nullable=False, default=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now(),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now(),
        onupdate=db.func.now(),
    )

    actions = db.relationship(
        "PermissionActionORM",
        back_populates="module",
        cascade="all, delete-orphan",
    )

    route_maps = db.relationship(
        "PermissionRouteMapORM",
        back_populates="module",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "key",
            name="uq_permission_modules_key",
        ),
    )


class PermissionActionORM(db.Model):
    __tablename__ = "permission_actions"

    id = db.Column(db.Integer, primary_key=True)

    module_id = db.Column(
        db.Integer,
        db.ForeignKey("permission_modules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    key = db.Column(db.String(120), nullable=False)
    full_key = db.Column(db.String(240), nullable=False)
    name = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=True)
    risk_level = db.Column(db.String(40), nullable=False, default="medium")

    is_active = db.Column(db.Boolean, nullable=False, default=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now(),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now(),
        onupdate=db.func.now(),
    )

    module = db.relationship(
        "PermissionModuleORM",
        back_populates="actions",
    )

    route_maps = db.relationship(
        "PermissionRouteMapORM",
        back_populates="action",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "full_key",
            name="uq_permission_actions_full_key",
        ),
        db.UniqueConstraint(
            "module_id",
            "key",
            name="uq_permission_actions_module_key",
        ),
    )


class PermissionRouteMapORM(db.Model):
    __tablename__ = "permission_route_map"

    id = db.Column(db.Integer, primary_key=True)

    method = db.Column(db.String(16), nullable=False)
    route = db.Column(db.Text, nullable=False)
    endpoint_function = db.Column(db.String(180), nullable=False)
    source_file = db.Column(db.Text, nullable=False)

    module_id = db.Column(
        db.Integer,
        db.ForeignKey("permission_modules.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action_id = db.Column(
        db.Integer,
        db.ForeignKey("permission_actions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    current_guard = db.Column(db.Text, nullable=True)
    current_scope = db.Column(db.Text, nullable=True)
    review_status = db.Column(db.String(80), nullable=False, default="pending")
    notes = db.Column(db.Text, nullable=True)

    is_active = db.Column(db.Boolean, nullable=False, default=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now(),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now(),
        onupdate=db.func.now(),
    )

    module = db.relationship(
        "PermissionModuleORM",
        back_populates="route_maps",
    )
    action = db.relationship(
        "PermissionActionORM",
        back_populates="route_maps",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "method",
            "route",
            "endpoint_function",
            name="uq_permission_route_map_method_route_endpoint",
        ),
    )
