"""Pytest configuration and shared fixtures for Fluxer integration tests."""

import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio

from fluxer.http import HTTPClient


@pytest.fixture(scope="session")
def bot_token() -> str:
    """Get the bot token from environment variable or use hardcoded token."""
    token = os.getenv("FLUXER_BOT_TOKEN")
    if not token:
        token = "bot_token"
    return token


@pytest_asyncio.fixture
async def http_client(bot_token: str) -> AsyncGenerator[HTTPClient, None]:
    """Create an HTTP client for testing.

    This fixture automatically handles setup and teardown.
    """
    client = HTTPClient(bot_token, is_bot=True)
    async with client:
        yield client


@pytest.fixture
def test_guild_id() -> int | None:
    """Get test guild ID from environment variable."""
    guild_id = os.getenv("FLUXER_TEST_GUILD_ID")
    if guild_id:
        return int(guild_id)
    return None


@pytest.fixture
def test_channel_id() -> int | None:
    """Get test channel ID from environment variable."""
    channel_id = os.getenv("FLUXER_TEST_CHANNEL_ID")
    if channel_id:
        return int(channel_id)
    return None
