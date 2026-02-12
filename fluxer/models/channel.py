from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..utils import snowflake_to_datetime

if TYPE_CHECKING:
    from ..http import HTTPClient
    from .embed import Embed
    from .message import Message


@dataclass(slots=True)
class Channel:
    """Represents a Fluxer channel (text, DM, voice, category, etc.)."""

    id: str
    type: int
    name: str | None = None
    guild_id: str | None = None
    position: int | None = None
    topic: str | None = None
    nsfw: bool = False
    parent_id: str | None = None

    _http: HTTPClient | None = field(default=None, repr=False)

    @classmethod
    def from_data(cls, data: dict[str, Any], http: HTTPClient | None = None) -> Channel:
        return cls(
            id=data["id"],
            type=data["type"],
            name=data.get("name"),
            guild_id=data.get("guild_id"),
            position=data.get("position"),
            topic=data.get("topic"),
            nsfw=data.get("nsfw", False),
            parent_id=data.get("parent_id"),
            _http=http,
        )

    @property
    def mention(self) -> str:
        return f"<#{self.id}>"

    @property
    def created_at(self) -> datetime:
        return snowflake_to_datetime(self.id)

    async def send(
        self,
        content: str | None = None,
        *,
        embed: Embed | None = None,
        embeds: list[Embed] | None = None,
    ) -> Message:
        """Send a message to this channel.

        Args:
            content: Text content of the message.
            embed: A single embed to include.
            embeds: Multiple embeds to include.

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
            self.id, content=content, embeds=embed_list
        )
        return Message.from_data(data, self._http)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Channel) and self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
