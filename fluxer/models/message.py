from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..utils import snowflake_to_datetime

if TYPE_CHECKING:
    from ..http import HTTPClient
    from .channel import Channel
    from .reaction import PartialEmoji, Reaction
    from .user import User


@dataclass(slots=True)
class Message:
    """Represents a message in a Fluxer channel."""

    id: int
    channel_id: int
    content: str
    author: User
    timestamp: str
    edited_timestamp: str | None = None
    guild_id: int | None = None
    embeds: list[dict[str, Any]] = field(default_factory=list)
    attachments: list[dict[str, Any]] = field(default_factory=list)
    mentions: list[User] = field(default_factory=list)
    pinned: bool = False
    reactions: list[Reaction] = field(default_factory=list)

    _http: HTTPClient | None = field(default=None, repr=False)
    _channel: Channel | None = field(default=None, repr=False)

    @classmethod
    def from_data(cls, data: dict[str, Any], http: HTTPClient | None = None) -> Message:
        from .reaction import Reaction
        from .user import User

        author = User.from_data(data["author"], http)
        mentions = [User.from_data(u, http) for u in data.get("mentions", [])]

        # Create message first without reactions
        message = cls(
            id=int(data["id"]),
            channel_id=int(data["channel_id"]),
            content=data.get("content", ""),
            author=author,
            timestamp=data["timestamp"],
            edited_timestamp=data.get("edited_timestamp"),
            guild_id=int(data["guild_id"]) if data.get("guild_id") else None,
            embeds=data.get("embeds", []),
            attachments=data.get("attachments", []),
            mentions=mentions,
            pinned=data.get("pinned", False),
            _http=http,
        )

        # Parse reactions and link them to the message
        reactions_data = data.get("reactions", [])
        message.reactions = [
            Reaction.from_data(r, http=http, message=message) for r in reactions_data
        ]

        return message

    @property
    def created_at(self) -> datetime:
        return snowflake_to_datetime(self.id)

    @property
    def channel(self) -> Channel | None:
        """The channel this message was sent in (if cached)."""
        return self._channel

    async def send(self, content: str | None = None, **kwargs: Any) -> Message:
        """Send a message to the same channel (without replying).

        Args:
            content: The message content.
            **kwargs: Additional arguments to pass to send_message (embed, embeds, etc.)

        Returns:
            The created Message object.
        """
        if self._http is None:
            raise RuntimeError("Message is not bound to an HTTP client")

        data = await self._http.send_message(
            self.channel_id,
            content=content,
            **kwargs,
        )
        return Message.from_data(data, self._http)

    async def reply(self, content: str | None = None, **kwargs: Any) -> Message:
        """Reply to this message with a message reference.

        Args:
            content: The message content.
            **kwargs: Additional arguments to pass to send_message (embed, embeds, etc.)

        Returns:
            The created Message object.
        """
        if self._http is None:
            raise RuntimeError("Message is not bound to an HTTP client")

        # Create message reference to reply to this message
        message_reference = {
            "message_id": str(self.id),
            "channel_id": str(self.channel_id),
        }
        if self.guild_id:
            message_reference["guild_id"] = str(self.guild_id)

        data = await self._http.send_message(
            self.channel_id,
            content=content,
            message_reference=message_reference,
            **kwargs,
        )
        return Message.from_data(data, self._http)

    async def send_to_channel(
        self, channel_id: int | str, content: str | None = None, **kwargs: Any
    ) -> Message:
        """Send a message to a different channel.

        This is a convenience method to send to another channel from the context
        of this message (e.g., forwarding content or sending notifications).

        Args:
            channel_id: The target channel ID.
            content: The message content.
            **kwargs: Additional arguments to pass to send_message (embed, embeds, etc.)

        Returns:
            The created Message object.
        """
        if self._http is None:
            raise RuntimeError("Message is not bound to an HTTP client")

        data = await self._http.send_message(channel_id, content=content, **kwargs)
        return Message.from_data(data, self._http)

    async def edit(self, content: str | None = None, **kwargs: Any) -> Message:
        """Edit this message."""
        if self._http is None:
            raise RuntimeError("Message is not bound to an HTTP client")
        data = await self._http.edit_message(
            self.channel_id, self.id, content=content, **kwargs
        )
        return Message.from_data(data, self._http)

    async def delete(self) -> None:
        """Delete this message."""
        if self._http is None:
            raise RuntimeError("Message is not bound to an HTTP client")
        await self._http.delete_message(self.channel_id, self.id)

    async def add_reaction(self, emoji: str | PartialEmoji) -> None:
        """Add a reaction to this message.

        Args:
            emoji: The emoji to react with (unicode string or PartialEmoji)

        Raises:
            Forbidden: You don't have permission to add reactions
            NotFound: The message doesn't exist
            HTTPException: Adding the reaction failed
        """
        if self._http is None:
            raise RuntimeError("Message is not bound to an HTTP client")
        await self._http.add_reaction(self.channel_id, self.id, emoji)

    async def remove_reaction(
        self, emoji: str | PartialEmoji, user: User | int | str = "@me"
    ) -> None:
        """Remove a reaction from this message.

        Args:
            emoji: The emoji to remove (unicode string or PartialEmoji)
            user: The user or user ID to remove the reaction from (default: @me)

        Raises:
            Forbidden: You don't have permission to remove this reaction
            NotFound: The message or reaction doesn't exist
            HTTPException: Removing the reaction failed
        """
        if self._http is None:
            raise RuntimeError("Message is not bound to an HTTP client")

        from .user import User as UserModel

        user_id = user.id if isinstance(user, UserModel) else user
        await self._http.delete_reaction(self.channel_id, self.id, emoji, user_id)

    async def clear_reactions(self) -> None:
        """Remove all reactions from this message.

        Raises:
            Forbidden: You don't have permission to clear reactions
            NotFound: The message doesn't exist
            HTTPException: Clearing reactions failed
        """
        if self._http is None:
            raise RuntimeError("Message is not bound to an HTTP client")
        await self._http.delete_all_reactions(self.channel_id, self.id)

    async def clear_reaction(self, emoji: str | PartialEmoji) -> None:
        """Remove all reactions of a specific emoji from this message.

        Args:
            emoji: The emoji to clear all reactions for (unicode string or PartialEmoji)

        Raises:
            Forbidden: You don't have permission to clear reactions
            NotFound: The message doesn't exist
            HTTPException: Clearing reactions failed
        """
        if self._http is None:
            raise RuntimeError("Message is not bound to an HTTP client")
        await self._http.delete_all_reactions_for_emoji(self.channel_id, self.id, emoji)

    # Internal methods for handling reaction updates from gateway events
    def _add_reaction(
        self, data: dict[str, Any], emoji: PartialEmoji, user_id: int
    ) -> Reaction:
        """Internal method to add a reaction to this message from gateway data.

        Args:
            data: Gateway reaction data
            emoji: The emoji that was reacted with
            user_id: The user who reacted

        Returns:
            The Reaction object that was added or updated
        """
        from .reaction import Reaction

        # Find existing reaction with this emoji
        for reaction in self.reactions:
            if reaction.emoji == emoji:
                # Update existing reaction
                reaction.count += 1
                if user_id == getattr(self._http, "_user_id", None):
                    reaction.me = True
                return reaction

        # Create new reaction
        reaction = Reaction(
            emoji=emoji, count=1, me=False, _message=self, _http=self._http
        )
        self.reactions.append(reaction)
        return reaction

    def _remove_reaction(
        self, data: dict[str, Any], emoji: PartialEmoji, user_id: int
    ) -> Reaction:
        """Internal method to remove a reaction from this message from gateway data.

        Args:
            data: Gateway reaction data
            emoji: The emoji that was removed
            user_id: The user who removed their reaction

        Returns:
            The Reaction object that was updated or removed
        """
        # Find the reaction
        for i, reaction in enumerate(self.reactions):
            if reaction.emoji == emoji:
                reaction.count -= 1
                if user_id == getattr(self._http, "_user_id", None):
                    reaction.me = False

                # Remove reaction if count reaches 0
                if reaction.count <= 0:
                    self.reactions.pop(i)

                return reaction

        raise ValueError(f"Reaction {emoji} not found on message")

    def _clear_emoji(self, emoji: PartialEmoji) -> Reaction | None:
        """Internal method to clear all reactions of a specific emoji.

        Args:
            emoji: The emoji to clear

        Returns:
            The Reaction object that was removed, or None if not found
        """
        for i, reaction in enumerate(self.reactions):
            if reaction.emoji == emoji:
                return self.reactions.pop(i)
        return None
