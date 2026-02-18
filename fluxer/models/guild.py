from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..utils import snowflake_to_datetime

if TYPE_CHECKING:
    from ..http import HTTPClient


@dataclass(slots=True)
class Guild:
    """Represents a Fluxer guild (server/community)."""

    id: int
    name: str | None = None
    icon: str | None = None
    owner_id: int | None = None
    member_count: int | None = None
    unavailable: bool = False

    _http: HTTPClient | None = field(default=None, repr=False)

    @classmethod
    def from_data(cls, data: dict[str, Any], http: HTTPClient | None = None) -> Guild:
        return cls(
            id=int(data["id"]),
            name=data.get("name"),
            icon=data.get("icon"),
            owner_id=int(data["owner_id"]) if data.get("owner_id") else None,
            member_count=data.get("member_count"),
            unavailable=data.get("unavailable", False),
            _http=http,
        )

    @property
    def created_at(self) -> datetime:
        return snowflake_to_datetime(self.id)

    @property
    def icon_url(self) -> str | None:
        if self.icon:
            ext = "gif" if self.icon.startswith("a_") else "png"
            return f"https://fluxerusercontent.com/icons/{self.id}/{self.icon}.{ext}"
        return None

    async def fetch_emojis(self) -> list[Any]:
        """Fetch all emojis in this guild.

        Returns:
            List of Emoji objects
        """
        if not self._http:
            raise RuntimeError("Cannot fetch emojis without HTTPClient")

        from .emoji import Emoji

        data = await self._http.get_guild_emojis(self.id)
        # Pass guild_id when creating emojis since API doesn't always return it
        return [
            Emoji.from_data(emoji_data, self._http, guild_id=self.id)
            for emoji_data in data
        ]

    # -- Role Management Methods --
    async def fetch_roles(self) -> list[Any]:
        """Fetch all roles in this guild.

        Returns:
            List of Role objects
        """
        if not self._http:
            raise RuntimeError("Cannot fetch roles without HTTPClient")

        from .role import Role

        data = await self._http.get_guild_roles(self.id)
        return [Role.from_data(role_data, self._http, guild_id=self.id) for role_data in data]

    async def create_role(
        self,
        *,
        name: str | None = None,
        permissions: int | None = None,
        color: int = 0,
        hoist: bool = False,
        mentionable: bool = False,
    ) -> Any:
        """Create a new role in this guild.

        Args:
            name: Role name
            permissions: Permission bitfield
            color: Role color
            hoist: Whether to display role separately
            mentionable: Whether role can be mentioned

        Returns:
            Role object
        """
        if not self._http:
            raise RuntimeError("Cannot create role without HTTPClient")

        from .role import Role

        data = await self._http.create_guild_role(
            self.id,
            name=name,
            permissions=permissions,
            color=color,
            hoist=hoist,
            mentionable=mentionable,
        )
        return Role.from_data(data, self._http, guild_id=self.id)

    # -- Member Management Methods --
    async def fetch_member(self, user_id: int) -> Any:
        """Fetch a specific member from this guild.

        Args:
            user_id: User ID to fetch

        Returns:
            GuildMember object
        """
        if not self._http:
            raise RuntimeError("Cannot fetch member without HTTPClient")

        from .member import GuildMember

        data = await self._http.get_guild_member(self.id, user_id)
        return GuildMember.from_data(data, self._http)

    async def fetch_members(self, *, limit: int = 100, after: int | None = None) -> list[Any]:
        """Fetch members from this guild.

        Args:
            limit: Maximum number of members to fetch (1-1000)
            after: Fetch members after this user ID

        Returns:
            List of GuildMember objects
        """
        if not self._http:
            raise RuntimeError("Cannot fetch members without HTTPClient")

        from .member import GuildMember

        data = await self._http.get_guild_members(self.id, limit=limit, after=after)
        return [GuildMember.from_data(member_data, self._http) for member_data in data]

    # -- Moderation Methods --
    async def kick(self, user_id: int, *, reason: str | None = None) -> None:
        """Kick a member from this guild.

        Args:
            user_id: User ID to kick
            reason: Reason for audit log
        """
        if not self._http:
            raise RuntimeError("Cannot kick member without HTTPClient")

        await self._http.kick_guild_member(self.id, user_id, reason=reason)

    async def ban(
        self,
        user_id: int,
        *,
        delete_message_days: int = 0,
        delete_message_seconds: int = 0,
        reason: str | None = None,
    ) -> None:
        """Ban a user from this guild.

        Args:
            user_id: User ID to ban
            delete_message_days: Number of days to delete messages for (0-7)
            delete_message_seconds: Number of seconds to delete messages for (0-604800)
            reason: Reason for audit log
        """
        if not self._http:
            raise RuntimeError("Cannot ban member without HTTPClient")

        await self._http.ban_guild_member(
            self.id,
            user_id,
            delete_message_days=delete_message_days,
            delete_message_seconds=delete_message_seconds,
            reason=reason,
        )

    async def unban(self, user_id: int, *, reason: str | None = None) -> None:
        """Unban a user from this guild.

        Args:
            user_id: User ID to unban
            reason: Reason for audit log
        """
        if not self._http:
            raise RuntimeError("Cannot unban user without HTTPClient")

        await self._http.unban_guild_member(self.id, user_id, reason=reason)

    def __str__(self) -> str:
        return self.name or f"Guild({self.id})"
