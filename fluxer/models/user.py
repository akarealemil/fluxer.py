from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..utils import snowflake_to_datetime

if TYPE_CHECKING:
    from ..http import HTTPClient


@dataclass(slots=True)
class User:
    """Represents a Fluxer user."""

    id: str
    username: str
    discriminator: str | None = None
    avatar: str | None = None
    bot: bool = False

    # Back-reference (set after construction)
    _http: HTTPClient | None = field(default=None, repr=False)

    @classmethod
    def from_data(cls, data: dict[str, Any], http: HTTPClient | None = None) -> User:
        return cls(
            id=data["id"],
            username=data["username"],
            discriminator=data.get("discriminator"),
            avatar=data.get("avatar"),
            bot=data.get("bot", False),
            _http=http,
        )

    @property
    def created_at(self) -> datetime:
        """When this user account was created (derived from Snowflake)."""
        return snowflake_to_datetime(self.id)

    @property
    def mention(self) -> str:
        """Return a string that mentions this user in a message."""
        return f"<@{self.id}>"

    @property
    def avatar_url(self) -> str | None:
        """URL for the user's avatar, or None if they use the default."""
        if self.avatar:
            ext = "gif" if self.avatar.startswith("a_") else "png"
            return (
                f"https://fluxerusercontent.com/avatars/{self.id}/{self.avatar}.{ext}"
            )
        return None

    @property
    def default_avatar_url(self) -> str:
        """URL for the user's default avatar."""
        index = int(self.id) % 6
        return f"https://fluxerstatic.com/avatars/{index}.png"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, User) and self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    def __str__(self) -> str:
        if self.discriminator:
            return f"{self.username}#{self.discriminator}"
        return self.username
