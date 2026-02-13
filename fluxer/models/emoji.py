from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..http import HTTPClient


@dataclass(slots=True)
class Emoji:
    """Represents a custom emoji in a Fluxer guild."""

    id: str
    name: str
    animated: bool = False
    guild_id: str | None = None
    roles: list[str] = field(default_factory=list)
    managed: bool = False
    available: bool = True

    _http: HTTPClient | None = field(default=None, repr=False)

    @classmethod
    def from_data(
        cls,
        data: dict[str, Any],
        http: HTTPClient | None = None,
        *,
        guild_id: str | None = None,
    ) -> Emoji:
        return cls(
            id=data["id"],
            name=data.get("name", ""),
            animated=data.get("animated", False),
            guild_id=guild_id or data.get("guild_id"),
            roles=data.get("roles", []),
            managed=data.get("managed", False),
            available=data.get("available", True),
            _http=http,
        )

    async def delete(self, *, reason: str | None = None) -> None:
        """Delete this emoji from its guild.

        Args:
            reason: Reason for deletion (shows in audit log)

        Raises:
            Forbidden: You don't have permission to delete emojis
            NotFound: Emoji doesn't exist
            HTTPException: Deleting the emoji failed
        """
        if not self._http:
            raise RuntimeError("Cannot delete emoji without HTTPClient")
        if not self.guild_id:
            raise RuntimeError("Cannot delete emoji without guild_id")

        await self._http.delete_guild_emoji(self.guild_id, self.id, reason=reason)

    def __str__(self) -> str:
        return f"<{'a' if self.animated else ''}:{self.name}:{self.id}>"
