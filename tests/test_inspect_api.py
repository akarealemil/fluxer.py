"""Quick inspection test to see what fields Fluxer API returns.

Run with pytest:
    pytest tests/test_inspect_api.py -v -s

Or run directly:
    python tests/test_inspect_api.py
"""

import asyncio
import json

import pytest

from fluxer.http import HTTPClient


@pytest.mark.asyncio
async def test_inspect_user_fields(http_client: HTTPClient) -> None:
    """Print out all fields returned by the user endpoint (pytest version)."""
    data = await http_client.get_current_user()

    print("\n" + "=" * 60)
    print("User object fields from Fluxer API:")
    print("=" * 60)
    print(json.dumps(data, indent=2))
    print("=" * 60)

    # List all keys
    print(f"\nAvailable fields: {list(data.keys())}")
    print()

    # Assert we at least got the basic fields
    assert "id" in data
    assert "username" in data
    assert "discriminator" in data


async def inspect_user_fields() -> None:
    """Print out all fields returned by the user endpoint (standalone version)."""
    token = "bot_token"

    async with HTTPClient(token) as http:
        data = await http.get_current_user()

        print("\n" + "=" * 60)
        print("User object fields from Fluxer API:")
        print("=" * 60)
        print(json.dumps(data, indent=2))
        print("=" * 60)

        # List all keys
        print(f"\nAvailable fields: {list(data.keys())}")
        print()


if __name__ == "__main__":
    asyncio.run(inspect_user_fields())
