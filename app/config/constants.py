"""
YouTube Internal API — Named Constants
---------------------------------------
Các giá trị này là protobuf-encoded params hoặc browseId cố định của YouTube.
Khi YouTube đổi cấu trúc, chỉ cần update tại đây.

Cách decode params: base64.b64decode(urllib.parse.unquote(value))
"""

# ── API endpoint names ──────────────────────────────────────────────────────
ENDPOINT_BROWSE  = "browse"   # channel, trending, playlist browse
ENDPOINT_SEARCH  = "search"   # search, live, location search
ENDPOINT_PLAYER  = "player"   # video detail / player info
ENDPOINT_NEXT    = "next"     # comments, replies, next page

# ── Browse IDs ──────────────────────────────────────────────────────────────
BROWSE_ID_TRENDING = "FEtrending"  # YouTube trending page

# ── Search filter params (URL-encoded base64 protobuf) ──────────────────────
# Decode: base64.b64decode(urllib.parse.unquote(SEARCH_FILTER_LIVE)) → b'\x1a\x02 \x01'
SEARCH_FILTER_LIVE     = "EgJAAQ%3D%3D"   # Live videos only
SEARCH_FILTER_LOCATION = "EgIIAQ%3D%3D"   # Location-based video filter

# ── Sort params for search ───────────────────────────────────────────────────
SORT_RELEVANCE   = None            # default
SORT_UPLOAD_DATE = "CAISAhAB"
SORT_VIEW_COUNT  = "CAMSAhAB"
SORT_RATING      = "CAESAhAB"

# ── Channel browse params (base64, NOT URL-encoded) ──────────────────────────
# Decode: base64.b64decode("EgZ2aWRlb3M=") → b'\x12\x06videos'
CHANNEL_TAB_VIDEOS = "EgZ2aWRlb3M"  # Videos tab filter for channel browse

# ── Trending category filter params ─────────────────────────────────────────
# Decode: base64.b64decode(urllib.parse.unquote(TRENDING_FILTER_MUSIC)) → b'\x1a\x06music\x00'
TRENDING_FILTER_NOW   = None                # All trending (no filter)
TRENDING_FILTER_MUSIC = "EgZtdXNpYw%3D%3D"
TRENDING_FILTER_GAMES = "EgZnYW1pbmc%3D"
TRENDING_FILTER_MOVIES = "EgZtb3ZpZXM%3D"

# ── Client info (bump clientVersion nếu YouTube trả 400) ────────────────────
CLIENT_NAME    = "WEB"
CLIENT_VERSION = "2.20250901.05.00"
CLIENT_HL      = "en"
CLIENT_GL      = "US"

# ── HTTP defaults ────────────────────────────────────────────────────────────
DEFAULT_TIMEOUT = 15   # seconds
