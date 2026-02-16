from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..http import HTTPClient

from .user import User


@dataclass(slots=True)
class GuildMember:
    """Represents a member of a guild.

    This combines a User object with guild-specific information like
    nickname, roles, join date, etc.
    """

    # The underlying user
    user: User

    # Guild-specific fields
    nick: str | None = None  # Guild nickname (overrides global_name)
    avatar_hash: str | None = None  # Guild-specific avatar hash
    banner: str | None = None  # Guild-specific banner
    accent_color: int | None = None  # Guild-specific accent color
    roles: list[int] = field(default_factory=list)  # Role IDs (as ints)
    joined_at: str | None = None  # ISO 8601 timestamp

    # Invite/join tracking
    join_source_type: int | None = None
    source_invite_code: str | None = None
    inviter_id: int | None = None

    # Voice state
    mute: bool = False
    deaf: bool = False

    # Moderation
    communication_disabled_until: str | None = None  # Timeout until (ISO 8601)

    # Back-reference (set after construction)
    _http: HTTPClient | None = field(default=None, repr=False)

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> GuildMember:
        # Parse the nested user object
        user = User.from_data(data["user"], http)

        return cls(
            user=user,
            nick=data.get("nick"),
            avatar_hash=data.get("avatar"),
            banner=data.get("banner"),
            accent_color=data.get("accent_color"),
            roles=[int(role_id) for role_id in data.get("roles", [])],
            joined_at=data.get("joined_at"),
            join_source_type=data.get("join_source_type"),
            source_invite_code=data.get("source_invite_code"),
            inviter_id=int(data["inviter_id"]) if data.get("inviter_id") else None,
            mute=data.get("mute", False),
            deaf=data.get("deaf", False),
            communication_disabled_until=data.get("communication_disabled_until"),
            _http=http,
        )

    @property
    def display_name(self) -> str:
        """The best display name for this member.

        Priority: guild nickname > global name > username
        """
        return self.nick or self.user.global_name or self.user.username

    @property
    def mention(self) -> str:
        """Return a string that mentions this member."""
        return f"<@{self.user.id}>"

    @property
    def guild_avatar_url(self) -> str | None:
        """URL for the member's guild-specific avatar, if set."""
        if self.avatar_hash:
            ext = "gif" if self.avatar_hash.startswith("a_") else "png"
            # Note: Guild avatar URLs might have a different format
            # Adjust if Fluxer uses a different URL structure
            return f"https://fluxerusercontent.com/guilds/avatars/{self.user.id}/{self.avatar_hash}.{ext}"
        return None

    @property
    def guild_id(self) -> int | None:
        """Get the guild ID from the HTTP client context if available."""
        # This is a helper for convenience methods that need guild_id
        # The guild_id should be stored in the member context
        # For now, we'll require it to be passed to methods
        return None

    # -- Role Management Methods --
    async def add_role(
        self, role_id: int, *, reason: str | None = None, guild_id: int
    ) -> None:
        """Add a role to this member.

        Args:
            role_id: Role ID to add
            reason: Reason for audit log
            guild_id: Guild ID (required)
        """
        if not self._http:
            raise RuntimeError("Cannot add role without HTTPClient")

        await self._http.add_guild_member_role(
            guild_id, self.user.id, role_id, reason=reason
        )
        # Update local role list
        if role_id not in self.roles:
            self.roles.append(role_id)

    async def remove_role(
        self, role_id: int, *, reason: str | None = None, guild_id: int
    ) -> None:
        """Remove a role from this member.

        Args:
            role_id: Role ID to remove
            reason: Reason for audit log
            guild_id: Guild ID (required)
        """
        if not self._http:
            raise RuntimeError("Cannot remove role without HTTPClient")

        await self._http.remove_guild_member_role(
            guild_id, self.user.id, role_id, reason=reason
        )
        # Update local role list
        if role_id in self.roles:
            self.roles.remove(role_id)

    def has_role(self, role_id: int) -> bool:
        """Check if this member has a specific role.

        Args:
            role_id: Role ID to check

        Returns:
            True if member has the role, False otherwise
        """
        return role_id in self.roles

    # -- Moderation Methods --
    async def kick(self, *, reason: str | None = None, guild_id: int) -> None:
        """Kick (remove) this member from the guild.

        Args:
            reason: Reason for audit log
            guild_id: Guild ID (required)
        """
        if not self._http:
            raise RuntimeError("Cannot kick member without HTTPClient")

        await self._http.kick_guild_member(guild_id, self.user.id, reason=reason)

    async def ban(
        self,
        *,
        delete_message_days: int = 0,
        delete_message_seconds: int = 0,
        reason: str | None = None,
        guild_id: int,
    ) -> None:
        """Ban this member from the guild.

        Args:
            delete_message_days: Number of days to delete messages for (0-7)
            delete_message_seconds: Number of seconds to delete messages for (0-604800)
            reason: Reason for audit log
            guild_id: Guild ID (required)
        """
        if not self._http:
            raise RuntimeError("Cannot ban member without HTTPClient")

        await self._http.ban_guild_member(
            guild_id,
            self.user.id,
            delete_message_days=delete_message_days,
            delete_message_seconds=delete_message_seconds,
            reason=reason,
        )

    async def timeout(
        self, *, until: str | None = None, reason: str | None = None, guild_id: int
    ) -> "GuildMember":
        """Timeout this member (or remove timeout).

        Args:
            until: ISO 8601 timestamp for when timeout expires (None to remove timeout)
            reason: Reason for audit log
            guild_id: Guild ID (required)

        Returns:
            Updated GuildMember object
        """
        if not self._http:
            raise RuntimeError("Cannot timeout member without HTTPClient")

        data = await self._http.timeout_guild_member(
            guild_id, self.user.id, until=until, reason=reason
        )
        # Update the local timeout field
        self.communication_disabled_until = data.get("communication_disabled_until")
        return self

    async def edit(
        self,
        *,
        nick: str | None = None,
        roles: list[int | str] | None = None,
        mute: bool | None = None,
        deaf: bool | None = None,
        channel_id: int | None = None,
        communication_disabled_until: str | None = None,
        reason: str | None = None,
        guild_id: int,
    ) -> "GuildMember":
        """Edit this member.

        Args:
            nick: New nickname (None to remove)
            roles: List of role IDs to set (replaces all roles)
            mute: Whether to mute in voice channels
            deaf: Whether to deafen in voice channels
            channel_id: Voice channel to move member to
            communication_disabled_until: Timeout timestamp (ISO 8601)
            reason: Reason for audit log
            guild_id: Guild ID (required)

        Returns:
            Updated GuildMember object
        """
        if not self._http:
            raise RuntimeError("Cannot edit member without HTTPClient")

        data = await self._http.modify_guild_member(
            guild_id,
            self.user.id,
            nick=nick,
            roles=roles,
            mute=mute,
            deaf=deaf,
            channel_id=channel_id,
            communication_disabled_until=communication_disabled_until,
            reason=reason,
        )
        # Update local fields
        if "nick" in data:
            self.nick = data["nick"]
        if "roles" in data:
            self.roles = [int(r) for r in data["roles"]]
        if "mute" in data:
            self.mute = data["mute"]
        if "deaf" in data:
            self.deaf = data["deaf"]
        if "communication_disabled_until" in data:
            self.communication_disabled_until = data["communication_disabled_until"]
        return self

    def __str__(self) -> str:
        """Return the member's display name."""
        return self.display_name
