"""Test fetching guild member data including nicknames and roles.

Usage:
    python examples/test_member.py <guild_id> <user_id>
"""

import asyncio
import sys

from fluxer.http import HTTPClient
from fluxer.models.member import GuildMember


async def main():
    token = "bot_token"

    if len(sys.argv) < 3:
        print("Usage: python examples/test_member.py <guild_id> <user_id>")
        print("\nExample:")
        print(
            "  python examples/test_member.py 1470940902728487571 1470560041931524138"
        )
        sys.exit(1)

    guild_id = sys.argv[1]
    user_id = sys.argv[2]

    async with HTTPClient(token) as http:
        print(f"Fetching member {user_id} from guild {guild_id}...\n")

        data = await http.get_guild_member(guild_id, user_id)
        member = GuildMember.from_data(data, http)

        print("=" * 60)
        print("Guild Member Information")
        print("=" * 60)

        # User info
        print(f"User ID:       {member.user.id}")
        print(f"Username:      {member.user.username}#{member.user.discriminator}")
        print(f"Global Name:   {member.user.global_name or '(not set)'}")
        print(f"Bot:           {member.user.bot}")

        # Guild-specific info
        print(f"\nGuild Nickname: {member.nick or '(not set)'}")
        print(f"Display Name:   {member.display_name} ⭐")
        print(f"str(member):    {str(member)}")

        # Roles
        print(f"\nRoles:          {len(member.roles)} role(s)")
        if member.roles:
            print(f"  Role IDs:     {member.roles}")

        # Join info
        print(f"\nJoined At:      {member.joined_at}")
        if member.inviter_id:
            print(f"Invited By:     {member.inviter_id}")

        # Voice state
        print(f"\nMuted:          {member.mute}")
        print(f"Deafened:       {member.deaf}")

        # Timeout
        if member.communication_disabled_until:
            print(f"Timed Out Until: {member.communication_disabled_until}")

        # Avatars
        print(
            f"\nUser Avatar:    {member.user.avatar_url or member.user.default_avatar_url}"
        )
        if member.guild_avatar_url:
            print(f"Guild Avatar:   {member.guild_avatar_url}")

        print("\n" + "=" * 60)
        print("Key Insight")
        print("=" * 60)
        print("✅ member.display_name = nick > global_name > username")
        print("   This is the name you should show in your guild!")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
