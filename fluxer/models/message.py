from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..utils import snowflake_to_datetime

if TYPE_CHECKING:
    from ..http import HTTPClient
    from .channel import Channel
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

    _http: HTTPClient | None = field(default=None, repr=False)
    _channel: Channel | None = field(default=None, repr=False)

    @classmethod
    def from_data(cls, data: dict[str, Any], http: HTTPClient | None = None) -> Message:
        from .user import User

        author = User.from_data(data["author"], http)
        mentions = [User.from_data(u, http) for u in data.get("mentions", [])]

        return cls(
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

    @property
    def created_at(self) -> datetime:
        return snowflake_to_datetime(self.id)

    @property
    def channel(self) -> Channel | None:
        """The channel this message was sent in (if cached)."""
        return self._channel

    async def reply(self, content: str, **kwargs: Any) -> Message:
        """Reply to this message."""
        if self._http is None:
            raise RuntimeError("Message is not bound to an HTTP client")
        data = await self._http.send_message(self.channel_id, content=content, **kwargs)
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

    async def add_reaction(self, emoji: str) -> None:
        """Add reaction to this message."""
        if self._http is None:
            raise RuntimeError("Message is not bound to an HTTP client")
        await self._http.add_reaction(self.channel_id, self.id, emoji)
