from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..enums import ChannelType
from ..utils import snowflake_to_datetime

if TYPE_CHECKING:
    from ..http import HTTPClient
    from .embed import Embed
    from .message import Message


@dataclass(slots=True)
class Channel:
    """Represents a Fluxer channel (text, DM, voice, category, etc.)."""

    id: int
    type: int
    name: str | None = None
    guild_id: int | None = None
    position: int | None = None
    topic: str | None = None
    nsfw: bool = False
    parent_id: int | None = None

    _http: HTTPClient | None = field(default=None, repr=False)

    @classmethod
    def from_data(cls, data: dict[str, Any], http: HTTPClient | None = None) -> Channel:
        return cls(
            id=int(data["id"]),
            type=data["type"],
            name=data.get("name"),
            guild_id=int(data["guild_id"]) if data.get("guild_id") else None,
            position=data.get("position"),
            topic=data.get("topic"),
            nsfw=data.get("nsfw", False),
            parent_id=int(data["parent_id"]) if data.get("parent_id") else None,
            _http=http,
        )

    @property
    def mention(self) -> str:
        return f"<#{self.id}>"

    @property
    def created_at(self) -> datetime:
        return snowflake_to_datetime(self.id)

    @property
    def is_text_channel(self) -> bool:
        """Whether this is a guild text channel."""
        return self.type == ChannelType.GUILD_TEXT

    @property
    def is_voice_channel(self) -> bool:
        """Whether this is a voice channel."""
        return self.type == ChannelType.GUILD_VOICE

    @property
    def is_dm(self) -> bool:
        """Whether this is a DM channel."""
        return self.type == ChannelType.DM

    @property
    def is_category(self) -> bool:
        """Whether this is a category channel."""
        return self.type == ChannelType.GUILD_CATEGORY

    async def send(
        self,
        content: str | None = None,
        *,
        embed: Embed | None = None,
        embeds: list[Embed] | None = None,
        files: list[dict[str, Any]] | None = None,
        message_reference: dict[str, Any] | None = None,
    ) -> Message:
        """Send a message to this channel.

        Args:
            content: Text content of the message.
            embed: A single embed to include.
            embeds: Multiple embeds to include.
            files: List of file objects to attach. Each file should be a dict with
                'data' (file bytes) and 'filename' (str) keys.
                Example: [{"data": file_bytes, "filename": "image.png"}]
            message_reference: Reference to another message for replies.

        Returns:
            The created Message object.
        """
        # Import here to avoid circular imports
        from .message import Message

        if self._http is None:
            raise RuntimeError("Channel is not bound to an HTTP client")

        embed_list: list[dict[str, Any]] | None = None
        if embed:
            embed_list = [embed.to_dict()]
        elif embeds:
            embed_list = [e.to_dict() for e in embeds]

        data = await self._http.send_message(
            self.id,
            content=content,
            embeds=embed_list,
            files=files,
            message_reference=message_reference,
        )
        return Message.from_data(data, self._http)

    async def fetch_message(self, message_id: int | str) -> Message:
        """Fetch a message from this channel by ID.

        Args:
            message_id: The message ID to fetch.

        Returns:
            The fetched Message object.
        """
        from .message import Message

        if self._http is None:
            raise RuntimeError("Channel is not bound to an HTTP client")

        data = await self._http.get_message(self.id, message_id)
        return Message.from_data(data, self._http)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Channel) and self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
