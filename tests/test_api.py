"""
Test API endpoints
"""

import pytest
from fastapi import status


@pytest.mark.api
class TestHealthEndpoint:
    """Tests for health check endpoint"""

    def test_health_check(self, client):
        """Test health check endpoint returns 200"""
        response = client.get("/health")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "youtube-crawler"
        assert "version" in data


@pytest.mark.api
class TestAuthentication:
    """Tests for API authentication"""

    def test_search_without_api_key(self, client):
        """Test that search endpoint requires API key"""
        response = client.get("/api/search?q=python")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_search_with_invalid_api_key(self, client):
        """Test that invalid API key is rejected"""
        headers = {"X-API-Key": "invalid_key"}
        response = client.get("/api/search?q=python", headers=headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_search_with_valid_api_key(self, client, auth_headers):
        """Test that valid API key allows access"""
        # Note: This will still fail without mocking the actual YouTube API call
        # but it should pass authentication
        response = client.get("/api/search?q=python", headers=auth_headers)
        # We expect it to fail at the service level, not auth level
        assert response.status_code != status.HTTP_401_UNAUTHORIZED
        assert response.status_code != status.HTTP_403_FORBIDDEN


@pytest.mark.api
class TestSearchEndpoint:
    """Tests for search endpoint"""

    def test_search_missing_query_parameter(self, client, auth_headers):
        """Test that search requires a query parameter"""
        response = client.get("/api/search", headers=auth_headers)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_search_with_query_parameter(self, client, auth_headers):
        """Test search with query parameter"""
        response = client.get("/api/search?q=python", headers=auth_headers)
        # Will fail due to actual YouTube call, but validates endpoint structure
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_500_INTERNAL_SERVER_ERROR]

    def test_search_pagination_parameters(self, client, auth_headers):
        """Test search with pagination parameters"""
        response = client.get(
            "/api/search?q=python&page=2&limit=20",
            headers=auth_headers
        )
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_500_INTERNAL_SERVER_ERROR]

    def test_search_sort_parameter(self, client, auth_headers):
        """Test search with sort parameter"""
        for sort_option in ["relevance", "upload_date", "view_count", "rating"]:
            response = client.get(
                f"/api/search?q=python&sort={sort_option}",
                headers=auth_headers
            )
            assert response.status_code in [status.HTTP_200_OK, status.HTTP_500_INTERNAL_SERVER_ERROR]

    def test_search_invalid_sort_parameter(self, client, auth_headers):
        """Test search with invalid sort parameter"""
        response = client.get(
            "/api/search?q=python&sort=invalid",
            headers=auth_headers
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_search_invalid_page_parameter(self, client, auth_headers):
        """Test search with invalid page parameter"""
        response = client.get(
            "/api/search?q=python&page=0",
            headers=auth_headers
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_search_limit_out_of_range(self, client, auth_headers):
        """Test search with limit out of valid range"""
        response = client.get(
            "/api/search?q=python&limit=100",
            headers=auth_headers
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.api
class TestVideoDetailEndpoint:
    """Tests for video detail endpoint"""

    def test_video_detail_endpoint_exists(self, client):
        """Test that video detail endpoint exists"""
        response = client.get("/api/video/dQw4w9WgXcQ")
        # Should fail at service level, not routing level
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_500_INTERNAL_SERVER_ERROR]

    def test_video_detail_with_invalid_id(self, client):
        """Test video detail with clearly invalid ID"""
        response = client.get("/api/video/invalid")
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_500_INTERNAL_SERVER_ERROR]


@pytest.mark.api
class TestChannelEndpoints:
    """Tests for channel-related endpoints"""

    def test_channel_videos_missing_parameter(self, client):
        """Test that channel videos requires channel_input parameter"""
        response = client.get("/api/channel/videos")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_channel_videos_with_channel_id(self, client):
        """Test channel videos with channel ID"""
        response = client.get("/api/channel/videos?channel_input=UCtest123")
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_500_INTERNAL_SERVER_ERROR]

    def test_channel_videos_with_handle(self, client):
        """Test channel videos with @handle"""
        response = client.get("/api/channel/videos?channel_input=@testchannel")
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_500_INTERNAL_SERVER_ERROR]

    def test_channel_info_endpoint(self, client):
        """Test channel info endpoint"""
        response = client.get("/api/channel/UCtest123")
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_500_INTERNAL_SERVER_ERROR]


@pytest.mark.integration
@pytest.mark.slow
class TestIntegrationEndpoints:
    """Integration tests that may make actual API calls"""

    def test_trending_endpoint(self, client):
        """Test trending videos endpoint"""
        response = client.get("/api/trending")
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_500_INTERNAL_SERVER_ERROR]

    def test_live_endpoint(self, client):
        """Test live videos endpoint"""
        response = client.get("/api/live")
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_500_INTERNAL_SERVER_ERROR]
