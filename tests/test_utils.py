"""
Test utility functions
"""

import pytest
from app.utils.api_key_generator import generate_api_key


@pytest.mark.unit
class TestAPIKeyGenerator:
    """Tests for API key generation"""

    def test_generate_api_key_default_length(self):
        """Test that API key is generated with default length"""
        api_key = generate_api_key()
        assert len(api_key) == 32
        assert isinstance(api_key, str)

    def test_generate_api_key_custom_length(self):
        """Test API key generation with custom length"""
        for length in [16, 32, 64, 128]:
            api_key = generate_api_key(length=length)
            assert len(api_key) == length

    def test_generate_api_key_uniqueness(self):
        """Test that generated API keys are unique"""
        keys = [generate_api_key() for _ in range(100)]
        # All keys should be unique
        assert len(keys) == len(set(keys))

    def test_generate_api_key_characters(self):
        """Test that API key contains only valid characters"""
        api_key = generate_api_key()
        # Should only contain alphanumeric characters
        assert api_key.isalnum()


@pytest.mark.unit
class TestLoggingConfiguration:
    """Tests for logging configuration"""

    def test_logger_initialization(self):
        """Test that logger can be initialized"""
        from app.config.logging_config import get_logger

        logger = get_logger("test")
        assert logger is not None
        assert logger.name == "youtube_crawler.test"

    def test_json_formatter(self):
        """Test JSON formatter"""
        import logging
        from app.config.logging_config import JSONFormatter

        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None
        )

        formatted = formatter.format(record)
        assert isinstance(formatted, str)
        # Should be valid JSON
        import json
        data = json.loads(formatted)
        assert "timestamp" in data
        assert "level" in data
        assert "message" in data
        assert data["message"] == "Test message"


@pytest.mark.unit
class TestAuthMiddleware:
    """Tests for authentication middleware"""

    def test_get_api_keys(self):
        """Test API key loading from environment"""
        from app.middleware.auth_middleware import get_api_keys

        keys = get_api_keys()
        assert isinstance(keys, set)
        assert len(keys) > 0

    def test_multiple_api_keys(self):
        """Test multiple API keys separated by comma"""
        import os
        from app.middleware.auth_middleware import get_api_keys

        # Set multiple keys
        os.environ["API_KEYS"] = "key1,key2,key3"
        keys = get_api_keys()

        assert len(keys) == 3
        assert "key1" in keys
        assert "key2" in keys
        assert "key3" in keys


@pytest.mark.unit
class TestSchedulerJobs:
    """Tests for scheduler jobs"""

    @pytest.mark.asyncio
    async def test_crawl_trending_videos_structure(self):
        """Test that crawl_trending_videos returns expected structure"""
        from app.scheduler.jobs import crawl_trending_videos

        # This will likely fail due to API call, but we test structure
        result = await crawl_trending_videos()

        assert isinstance(result, dict)
        assert "success" in result

        if result["success"]:
            assert "videos_count" in result
            assert "duration" in result
        else:
            assert "error" in result

    @pytest.mark.asyncio
    async def test_health_check_job(self):
        """Test health check job"""
        from app.scheduler.jobs import health_check_job

        result = await health_check_job()

        assert isinstance(result, dict)
        assert "success" in result

        if result["success"]:
            assert "timestamp" in result
        else:
            assert "error" in result


@pytest.mark.unit
class TestConfigurationHeaders:
    """Tests for headers configuration"""

    def test_get_headers_returns_dict(self):
        """Test that get_headers returns a dictionary"""
        from app.config.headers import get_headers

        headers = get_headers()
        assert isinstance(headers, dict)

    def test_headers_contain_required_fields(self):
        """Test that headers contain required fields"""
        from app.config.headers import get_headers

        headers = get_headers()

        # Check for essential headers
        assert "User-Agent" in headers
        assert "Accept" in headers
        assert "Accept-Language" in headers

    def test_headers_randomization(self):
        """Test that headers are randomized between calls"""
        from app.config.headers import get_headers

        # Generate multiple headers
        headers_list = [get_headers() for _ in range(10)]

        # User-Agent should vary (due to randomization)
        user_agents = [h["User-Agent"] for h in headers_list]
        # At least some variation should exist
        assert len(set(user_agents)) > 1
