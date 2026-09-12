"""Maintenance Planner V2.

Feature module intentionally isolated from legacy PM.  Its public surface is the
blueprint exported here; domain reads/writes are kept inside the package so the
module can later be moved or replaced without leaking implementation details.
"""

from .routes import maintenance_planner_bp

__all__ = ["maintenance_planner_bp"]
