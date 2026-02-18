from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..utils import snowflake_to_datetime

if TYPE_CHECKING:
    from ..http import HTTPClient


@dataclass(slots=True)
class Role:
    """Represents a guild role."""

    id: int
    name: str
    color: int = 0  # RGB color value
    hoist: bool = False  # Whether role is displayed separately in member list
    position: int = 0  # Position in role hierarchy
    permissions: int = 0  # Permission bitfield
    managed: bool = False  # Whether role is managed by an integration
    mentionable: bool = False  # Whether role can be mentioned

    # Guild reference
    guild_id: int | None = None

    # Back-reference (set after construction)
    _http: HTTPClient | None = field(default=None, repr=False)

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None, guild_id: int | None = None
    ) -> Role:
        """Create a Role from API data.

        Args:
            data: Role data from API
            http: HTTP client for making requests
            guild_id: Guild ID (may not be in data for some endpoints)
        """
        return cls(
            id=int(data["id"]),
            name=data.get("name", ""),
            color=data.get("color", 0),
            hoist=data.get("hoist", False),
            position=data.get("position", 0),
            permissions=int(data.get("permissions", 0)),
            managed=data.get("managed", False),
            mentionable=data.get("mentionable", False),
            guild_id=guild_id or (int(data["guild_id"]) if data.get("guild_id") else None),
            _http=http,
        )

    @property
    def created_at(self) -> datetime:
        """When this role was created (derived from Snowflake)."""
        return snowflake_to_datetime(self.id)

    @property
    def mention(self) -> str:
        """Return a string that mentions this role in a message."""
        return f"<@&{self.id}>"

    @property
    def is_default(self) -> bool:
        """Whether this is the @everyone role."""
        return self.guild_id == self.id if self.guild_id else False

    async def edit(
        self,
        *,
        name: str | None = None,
        permissions: int | None = None,
        color: int | None = None,
        hoist: bool | None = None,
        mentionable: bool | None = None,
        reason: str | None = None,
    ) -> Role:
        """Edit this role.

        Args:
            name: New name
            permissions: New permissions bitfield
            color: New color
            hoist: Whether to display role separately
            mentionable: Whether role can be mentioned
            reason: Reason for audit log

        Returns:
            Updated Role object
        """
        if not self._http or not self.guild_id:
            raise RuntimeError("Cannot edit role without HTTPClient and guild_id")

        data = await self._http.modify_guild_role(
            self.guild_id,
            self.id,
            name=name,
            permissions=permissions,
            color=color,
            hoist=hoist,
            mentionable=mentionable,
        )
        return Role.from_data(data, self._http, self.guild_id)

    async def delete(self, *, reason: str | None = None) -> None:
        """Delete this role.

        Args:
            reason: Reason for audit log
        """
        if not self._http or not self.guild_id:
            raise RuntimeError("Cannot delete role without HTTPClient and guild_id")

        await self._http.delete_guild_role(self.guild_id, self.id)

    def __str__(self) -> str:
        return self.name

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Role) and self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    def __lt__(self, other: object) -> bool:
        """Roles are ordered by position (higher position = higher in hierarchy)."""
        if not isinstance(other, Role):
            return NotImplemented
        return self.position < other.position
