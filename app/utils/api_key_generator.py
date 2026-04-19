"""
Utility to generate secure API keys
"""

import secrets
import string


def generate_api_key(length: int = 32) -> str:
    """
    Generate a secure random API key

    Args:
        length: Length of the API key (default: 32)

    Returns:
        Random API key string
    """
    alphabet = string.ascii_letters + string.digits
    api_key = ''.join(secrets.choice(alphabet) for _ in range(length))
    return api_key


if __name__ == "__main__":
    print("Generated API Keys:")
    print("-" * 50)
    for i in range(3):
        print(f"API_KEY_{i + 1}: {generate_api_key()}")
    print("-" * 50)
    print("\nAdd these to your .env file:")
    print("API_KEYS=key1,key2,key3")
