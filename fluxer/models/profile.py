from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .user import User

if TYPE_CHECKING:
    from ..http import HTTPClient


@dataclass(slots=True)
class UserProfile:
    """Represents a Fluxer user's full profile.

    This contains profile information that is only available via the
    GET /users/{id}/profile endpoint, not from basic user objects.
    """

    # The basic user object
    user: User

    # Profile information
    bio: str | None = None
    pronouns: str | None = None
    banner: str | None = None  # Banner image hash
    banner_color: int | None = None
    accent_color: int | None = None

    # Premium information
    premium_type: int | None = None
    premium_since: str | None = None  # ISO 8601 timestamp
    premium_lifetime_sequence: int | None = None

    # Back-reference (set after construction)
    _http: HTTPClient | None = field(default=None, repr=False)

    @classmethod
    def from_data(
        cls, data: dict[str, Any], http: HTTPClient | None = None
    ) -> UserProfile:
        """Construct a UserProfile from raw API data.

        Args:
            data: Raw profile object from GET /users/{id}/profile
            http: HTTPClient for making further requests

        Returns:
            A new UserProfile instance
        """
        # Parse the nested user object
        user = User.from_data(data["user"], http)

        # Get the user_profile section
        profile_data = data.get("user_profile", {})

        return cls(
            user=user,
            bio=profile_data.get("bio"),
            pronouns=profile_data.get("pronouns"),
            banner=profile_data.get("banner"),
            banner_color=profile_data.get("banner_color"),
            accent_color=profile_data.get("accent_color"),
            premium_type=data.get("premium_type"),
            premium_since=data.get("premium_since"),
            premium_lifetime_sequence=data.get("premium_lifetime_sequence"),
            _http=http,
        )

    @property
    def banner_url(self) -> str | None:
        """URL for the user's banner, or None if they don't have one."""
        if self.banner:
            ext = "gif" if self.banner.startswith("a_") else "png"
            return f"https://fluxerusercontent.com/banners/{self.user.id}/{self.banner}.{ext}"
        return None

    @property
    def is_premium(self) -> bool:
        """Whether this user has premium."""
        return self.premium_type is not None and self.premium_type > 0

    def __str__(self) -> str:
        """Return the user's display name."""
        return self.user.display_name
