from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..http import HTTPClient
    from .message import Message
    from .user import User


@dataclass(slots=True)
class PartialEmoji:
    """Represents a partial emoji (used in reactions).

    This can be either a custom emoji or a unicode emoji.
    """

    name: str | None = None
    id: int | None = None
    animated: bool = False

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> PartialEmoji:
        """Create a PartialEmoji from gateway data."""
        emoji_id = data.get("id")
        return cls(
            name=data.get("name"),
            id=int(emoji_id) if emoji_id else None,
            animated=data.get("animated", False),
        )

    @property
    def is_unicode_emoji(self) -> bool:
        """Whether this is a unicode emoji (vs custom emoji)."""
        return self.id is None

    @property
    def is_custom_emoji(self) -> bool:
        """Whether this is a custom emoji."""
        return self.id is not None

    def __str__(self) -> str:
        """String representation of the emoji."""
        if self.is_unicode_emoji:
            return self.name or ""
        return f"<{'a' if self.animated else ''}:{self.name}:{self.id}>"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, PartialEmoji):
            return self.id == other.id and self.name == other.name
        return False

    def __hash__(self) -> int:
        return hash((self.id, self.name))


@dataclass(slots=True)
class Reaction:
    """Represents a reaction to a message.

    Attributes:
        emoji: The emoji used for this reaction
        count: Number of times this reaction was made
        me: Whether the current user reacted with this emoji
        message: The message this reaction is attached to
    """

    emoji: PartialEmoji
    count: int = 0
    me: bool = False

    _message: Message | None = field(default=None, repr=False)
    _http: HTTPClient | None = field(default=None, repr=False)

    @classmethod
    def from_data(
        cls,
        data: dict[str, Any],
        http: HTTPClient | None = None,
        message: Message | None = None,
    ) -> Reaction:
        """Create a Reaction from API data."""
        emoji = PartialEmoji.from_data(data["emoji"])
        return cls(
            emoji=emoji,
            count=data.get("count", 0),
            me=data.get("me", False),
            _message=message,
            _http=http,
        )

    @property
    def message(self) -> Message | None:
        """The message this reaction is on."""
        return self._message

    async def remove(self, user: User | int | str) -> None:
        """Remove this reaction from a specific user.

        Args:
            user: The user or user ID to remove the reaction from

        Raises:
            Forbidden: You don't have permission to remove this reaction
            NotFound: The message or reaction doesn't exist
            HTTPException: Removing the reaction failed
        """
        if not self._http or not self._message:
            raise RuntimeError("Cannot remove reaction without HTTPClient and Message")

        from .user import User as UserModel

        user_id = user.id if isinstance(user, UserModel) else user
        await self._http.delete_reaction(
            self._message.channel_id, self._message.id, self.emoji, user_id
        )

    async def clear(self) -> None:
        """Remove all instances of this reaction from the message.

        Raises:
            Forbidden: You don't have permission to clear reactions
            NotFound: The message doesn't exist
            HTTPException: Clearing reactions failed
        """
        if not self._http or not self._message:
            raise RuntimeError("Cannot clear reaction without HTTPClient and Message")

        await self._http.delete_all_reactions_for_emoji(
            self._message.channel_id, self._message.id, self.emoji
        )

    def __str__(self) -> str:
        return str(self.emoji)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Reaction):
            return self.emoji == other.emoji
        return False

    def __hash__(self) -> int:
        return hash(self.emoji)


@dataclass(slots=True)
class RawReactionActionEvent:
    """Represents a raw reaction add/remove event from the gateway.

    This event is dispatched even when the message is not in the internal cache.
    """

    message_id: int
    channel_id: int
    guild_id: int | None
    user_id: int
    emoji: PartialEmoji
    event_type: str  # "REACTION_ADD" or "REACTION_REMOVE"

    @classmethod
    def from_data(cls, data: dict[str, Any], event_type: str) -> RawReactionActionEvent:
        """Create a RawReactionActionEvent from gateway data."""
        emoji = PartialEmoji.from_data(data["emoji"])
        return cls(
            message_id=int(data["message_id"]),
            channel_id=int(data["channel_id"]),
            guild_id=int(data["guild_id"]) if data.get("guild_id") else None,
            user_id=int(data["user_id"]),
            emoji=emoji,
            event_type=event_type,
        )


@dataclass(slots=True)
class RawReactionClearEvent:
    """Represents a raw reaction clear event (all reactions removed from a message)."""

    message_id: int
    channel_id: int
    guild_id: int | None

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> RawReactionClearEvent:
        """Create a RawReactionClearEvent from gateway data."""
        return cls(
            message_id=int(data["message_id"]),
            channel_id=int(data["channel_id"]),
            guild_id=int(data["guild_id"]) if data.get("guild_id") else None,
        )


@dataclass(slots=True)
class RawReactionClearEmojiEvent:
    """Represents a raw reaction clear emoji event (all reactions of a specific emoji removed)."""

    message_id: int
    channel_id: int
    guild_id: int | None
    emoji: PartialEmoji

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> RawReactionClearEmojiEvent:
        """Create a RawReactionClearEmojiEvent from gateway data."""
        emoji = PartialEmoji.from_data(data["emoji"])
        return cls(
            message_id=int(data["message_id"]),
            channel_id=int(data["channel_id"]),
            guild_id=int(data["guild_id"]) if data.get("guild_id") else None,
            emoji=emoji,
        )
