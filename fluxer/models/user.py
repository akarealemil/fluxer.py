from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..utils import snowflake_to_datetime

if TYPE_CHECKING:
    from ..http import HTTPClient


@dataclass(slots=True)
class User:
    """Represents a Fluxer user.

    This contains fields that are available across most endpoints (guild members,
    message authors, etc.). Some fields like bio, banner, and banner_color are
    ONLY available when fetching your own user via GET /users/@me, not when
    fetching other users via GET /users/{user_id}.

    Fields that are ONLY in GET /users/@me:
    - bio: User's bio/about me text
    - banner: Banner image hash
    - banner_color: Banner color
    - email, phone: Contact info
    - premium fields, MFA status, etc.
    """

    # Core identity fields (available everywhere)
    id: int
    username: str
    discriminator: str | None = None
    global_name: str | None = None  # Display name/nickname
    avatar_hash: str | None = None
    avatar_color: str | None = None
    bot: bool = False
    flags: int = 0

    # Additional profile fields (may not be available for all users)
    bio: str | None = None  # User bio/about me
    banner_hash: str | None = None  # Banner image hash
    banner_color: int | None = None  # Banner color (integer)

    # Back-reference (set after construction)
    _http: HTTPClient | None = field(default=None, repr=False)

    @classmethod
    def from_data(cls, data: dict[str, Any], http: HTTPClient | None = None) -> User:
        return cls(
            id=int(data["id"]),
            username=data["username"],
            discriminator=data.get("discriminator"),
            global_name=data.get("global_name"),
            avatar_hash=data.get("avatar"),
            avatar_color=data.get("avatar_color"),
            bot=data.get("bot", False),
            flags=data.get("flags", 0),
            bio=data.get("bio"),
            banner_hash=data.get("banner"),
            banner_color=data.get("banner_color"),
            _http=http,
        )

    @property
    def created_at(self) -> datetime:
        """When this user account was created (derived from Snowflake)."""
        return snowflake_to_datetime(self.id)

    @property
    def display_name(self) -> str:
        """The best display name for this user.

        Returns global_name if set, otherwise falls back to username.
        This is the name you should show to users.
        """
        return self.global_name or self.username

    @property
    def mention(self) -> str:
        """Return a string that mentions this user in a message."""
        return f"<@{self.id}>"

    @property
    def avatar_url(self) -> str | None:
        """URL for the user's avatar, or None if they use the default."""
        if self.avatar_hash:
            ext = "gif" if self.avatar_hash.startswith("a_") else "png"
            return f"https://fluxerusercontent.com/avatars/{self.id}/{self.avatar_hash}.{ext}"
        return None

    @property
    def default_avatar_url(self) -> str:
        """URL for the user's default avatar."""
        index = int(self.id) % 6
        return f"https://fluxerstatic.com/avatars/{index}.png"

    @property
    def banner_url(self) -> str | None:
        """URL for the user's banner, or None if they don't have one."""
        if self.banner_hash:
            ext = "gif" if self.banner_hash.startswith("a_") else "png"
            return f"https://fluxerusercontent.com/banners/{self.id}/{self.banner_hash}.{ext}"
        return None

    def __eq__(self, other: object) -> bool:
        return isinstance(other, User) and self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    def __str__(self) -> str:
        """Return the user's display name.

        Uses global_name if available, otherwise username.
        """
        return self.global_name or self.username
