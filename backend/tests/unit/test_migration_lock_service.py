"""Tests for the migration lock service."""

from unittest.mock import MagicMock
from unittest.mock import patch

import pytest


class TestMigrationLockService:
    """Unit tests for MigrationLockService."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        """Create a fresh service instance with mocked Redis for each test."""
        from app.services.migration_lock_service import MigrationLockService

        self.service = MigrationLockService(redis_url="redis://fake:6379/0")
        self.mock_redis = MagicMock()
        self.mock_redis.ping.return_value = True
        self.service._client = self.mock_redis

    # ---- activate ----

    def test_activate_acquires_lock(self):
        self.mock_redis.set.return_value = True  # NX succeeded
        assert self.service.activate() is True
        self.mock_redis.set.assert_called_once()
        call_kwargs = self.mock_redis.set.call_args
        assert call_kwargs.kwargs["nx"] is True
        assert call_kwargs.kwargs["ex"] == 4 * 60 * 60

    def test_activate_fails_when_already_held(self):
        self.mock_redis.set.return_value = False  # NX failed — key exists
        assert self.service.activate() is False

    def test_activate_returns_false_when_redis_unavailable(self):
        self.service._client = None
        # Patch from_url to fail
        with patch("app.services.migration_lock_service.redis") as mock_mod:
            mock_mod.from_url.side_effect = ConnectionError("down")
            assert self.service.activate() is False

    # ---- deactivate ----

    def test_deactivate_releases_lock(self):
        self.mock_redis.delete.return_value = 1
        assert self.service.deactivate() is True
        self.mock_redis.delete.assert_called_once()

    def test_deactivate_returns_false_when_no_key(self):
        self.mock_redis.delete.return_value = 0
        assert self.service.deactivate() is False

    # ---- is_active ----

    def test_is_active_true_when_key_exists(self):
        self.mock_redis.exists.return_value = 1
        assert self.service.is_active() is True

    def test_is_active_false_when_key_missing(self):
        self.mock_redis.exists.return_value = 0
        assert self.service.is_active() is False

    def test_is_active_false_when_redis_unavailable(self):
        self.service._client = None
        with patch("app.services.migration_lock_service.redis") as mock_mod:
            mock_mod.from_url.side_effect = ConnectionError("down")
            assert self.service.is_active() is False

    # ---- refresh_ttl ----

    def test_refresh_ttl_resets_expiry(self):
        self.mock_redis.expire.return_value = True
        assert self.service.refresh_ttl() is True
        self.mock_redis.expire.assert_called_once()

    def test_refresh_ttl_custom_value(self):
        self.mock_redis.expire.return_value = True
        self.service.refresh_ttl(ttl=600)
        args = self.mock_redis.expire.call_args
        assert args[0][1] == 600

    def test_refresh_ttl_false_when_key_missing(self):
        self.mock_redis.expire.return_value = False
        assert self.service.refresh_ttl() is False

    # ---- lifecycle ----

    def test_activate_then_deactivate(self):
        self.mock_redis.set.return_value = True
        self.mock_redis.exists.return_value = 1
        self.mock_redis.delete.return_value = 1

        assert self.service.activate() is True
        assert self.service.is_active() is True
        assert self.service.deactivate() is True
