"""
Pytest configuration and fixtures
"""

import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture(scope="session")
def test_api_key():
    """Provide a test API key"""
    return "test_api_key_12345"


@pytest.fixture(scope="session", autouse=True)
def setup_test_env(test_api_key):
    """
    Setup test environment variables
    Auto-used for all tests
    """
    os.environ["API_KEYS"] = test_api_key
    os.environ["LOG_LEVEL"] = "DEBUG"
    os.environ["ENABLE_SCHEDULER"] = "false"  # Disable scheduler in tests
    os.environ["YOUTUBE_BASE_URL"] = "https://www.youtube.com"
    os.environ["YOUTUBE_API_BASE"] = "https://www.youtube.com/youtubei/v1"


@pytest.fixture
def client():
    """
    Create a test client for the FastAPI application
    """
    # Import here to ensure environment variables are set
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers(test_api_key):
    """
    Provide authentication headers for API requests
    """
    return {"X-API-Key": test_api_key}


@pytest.fixture
def mock_httpx_client():
    """
    Mock httpx AsyncClient for testing services
    """
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "contents": {
            "twoColumnSearchResultsRenderer": {
                "primaryContents": {
                    "sectionListRenderer": {
                        "contents": []
                    }
                }
            }
        }
    }
    mock_client.post.return_value = mock_response
    return mock_client


@pytest.fixture
def sample_video_data():
    """
    Provide sample video data for testing
    """
    return {
        "videoId": "dQw4w9WgXcQ",
        "title": "Sample Video Title",
        "duration": "3:30",
        "views": "1000000",
        "channel": "Sample Channel",
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "thumbnails": [
            {
                "url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/default.jpg",
                "width": 120,
                "height": 90
            }
        ]
    }


@pytest.fixture
def sample_channel_data():
    """
    Provide sample channel data for testing
    """
    return {
        "channelId": "UC123456789",
        "handle": "@samplechannel",
        "title": "Sample Channel",
        "description": "This is a sample channel",
        "subscriberCount": "100K subscribers",
        "avatar": {
            "thumbnails": [
                {
                    "url": "https://yt3.ggpht.com/sample/avatar.jpg",
                    "width": 88,
                    "height": 88
                }
            ]
        }
    }


@pytest.fixture
def sample_search_results():
    """
    Provide sample search results for testing
    """
    return {
        "query": "python tutorial",
        "page": 1,
        "limit": 10,
        "total": 3,
        "results": [
            {
                "videoId": "video1",
                "title": "Python Tutorial 1",
                "duration": "10:00",
                "views": "10000"
            },
            {
                "videoId": "video2",
                "title": "Python Tutorial 2",
                "duration": "15:00",
                "views": "20000"
            },
            {
                "videoId": "video3",
                "title": "Python Tutorial 3",
                "duration": "20:00",
                "views": "30000"
            }
        ]
    }
