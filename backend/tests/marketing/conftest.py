"""Synthetic environment bootstrap for isolated marketing unit tests.

No production credentials or provider endpoints are used here. Existing CI or
operator-provided values are never replaced.
"""
import os

os.environ.setdefault("SECRET_KEY", "local-marketing-tests-only-not-production")
os.environ.setdefault("JWT_SECRET_KEY", "local-marketing-jwt-tests-only-not-production")
os.environ.setdefault("CAMPAIGN_V2_PROVIDER_SEND_ENABLED", "false")
