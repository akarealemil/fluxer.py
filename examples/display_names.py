"""Example: Working with user display names and nicknames.

This example shows how to access a user's global display name (nickname)
vs their username.

Usage:
    python examples/display_names.py

Or with environment variable:
    export FLUXER_BOT_TOKEN="your_token_here"  # Linux/Mac
    $env:FLUXER_BOT_TOKEN="your_token_here"    # Windows PowerShell
    python examples/display_names.py
"""

import asyncio
import sys

from fluxer.http import HTTPClient
from fluxer.models.user import User


async def main():
    token = "bot_token"

    # Optional: Specify a user ID to fetch (otherwise fetches bot user)
    user_id = sys.argv[1] if len(sys.argv) > 1 else None

    # Initialize HTTP client (use async context manager for proper cleanup)
    async with HTTPClient(token) as http:
        # Fetch user
        if user_id:
            print(f"Fetching user {user_id}...")
            data = await http.get_user(user_id)
        else:
            print("Fetching current bot user...")
            data = await http.get_current_user()

        user = User.from_data(data, http)

        print("=" * 60)
        print("User Information")
        print("=" * 60)

        # ID: Unique user identifier
        print(f"ID:            {user.id}")

        # username: The account's unique username (e.g., "emil")
        print(f"Username:      {user.username}")

        # discriminator: The 4-digit discriminator (e.g., "0000")
        print(f"Discriminator: {user.discriminator}")

        # global_name: The user's chosen display name/nickname
        print(f"Global Name:   {user.global_name or '(not set)'}")

        # display_name: Convenience property that returns global_name or username
        # This is what you should show to users!
        print(f"Display Name:  {user.display_name}")

        # str(user): Also returns the display name
        print(f"str(user):     {str(user)}")

        print("\n" + "=" * 60)
        print("Other User Fields")
        print("=" * 60)
        print(f"Bot:           {user.bot}")
        print(f"Flags:         {user.flags}")
        print(f"Avatar Hash:   {user.avatar_hash or '(none)'}")
        print(f"Avatar Color:  {user.avatar_color or '(none)'}")
        if user.avatar_color:
            print(f"  (as hex):    #{user.avatar_color:06X}")
        print(f"Avatar URL:    {user.avatar_url or user.default_avatar_url}")
        print(f"Created At:    {user.created_at}")

        print("\n" + "=" * 60)
        print("Best Practices")
        print("=" * 60)
        print("✅ Use user.display_name or str(user) when showing names to users")
        print("✅ Use user.username for logging/debugging")
        print("✅ Use user.id for unique identification")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
