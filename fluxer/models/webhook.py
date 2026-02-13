from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from fluxer.models.user import User

if TYPE_CHECKING:
    from ..http import HTTPClient
    from .message import Message


@dataclass(slots=True)
class Webhook:
    """Represents a Fluxer webhook."""

    id: str
    guild_id: str
    channel_id: str
    user: User
    name: str
    avatar: str | None
    token: str

    _http: HTTPClient | None = field(default=None, repr=False)

    @classmethod
    def from_data(
        cls,
        data: dict[str, Any],
        http: HTTPClient | None = None,
        *,
        guild_id: str | None = None,
    ) -> Webhook:
        """Construct a Webhook from raw API data.

        Args:
            data: Raw webhook object from the API.
            http: HTTPClient for making further requests.
            guild_id: Override guild_id if not present in data.

        Returns:
            A new Webhook instance.
        """
        return cls(
            id=data["id"],
            guild_id=guild_id or data["guild_id"],
            channel_id=data["channel_id"],
            user=User.from_data(data["user"], http),
            name=data["name"],
            avatar=data.get("avatar", None),
            token=data["token"],
            _http=http,
        )

    async def edit(
        self,
        *,
        name: str | None = None,
        avatar: str | None = None,
        channel_id: str | None = None,
    ) -> Webhook:
        """Edit this webhook.

        Args:
            name: New webhook name.
            avatar: New avatar (base64 data URI).
            channel_id: Move webhook to a different channel.

        Returns:
            The updated Webhook.
        """
        if not self._http:
            raise RuntimeError("Cannot edit webhook without HTTPClient")

        data = await self._http.modify_webhook(
            self.id, name=name, avatar=avatar, channel_id=channel_id
        )
        return Webhook.from_data(data, self._http)

    async def send(
        self,
        content: str | None = None,
        *,
        embeds: list[dict[str, Any]] | None = None,
        username: str | None = None,
        avatar_url: str | None = None,
        wait: bool = False,
    ) -> Message | None:
        """Send a message with this webhook.

        Args:
            content: Text content of the message.
            embeds: List of embed dicts to include.
            username: Override the webhook's default name.
            avatar_url: Override the webhook's default avatar.
            wait: If True, returns the created Message.

        Returns:
            The created Message if wait=True, otherwise None.
        """
        if not self._http:
            raise RuntimeError("Cannot send with webhook without HTTPClient")

        data = await self._http.execute_webhook(
            self.id,
            self.token,
            content=content,
            embeds=embeds,
            username=username,
            avatar_url=avatar_url,
            wait=wait,
        )
        if data is not None:
            from .message import Message

            return Message.from_data(data, self._http)
        return None

    async def delete(self, *, reason: str | None = None) -> None:
        """Delete this webhook.

        Args:
            reason: Reason for deletion (shows in audit log)

        Raises:
            Forbidden: You don't have permission to delete this webhook
            NotFound: Webhook doesn't exist
            HTTPException: Deleting the webhook failed
        """
        if not self._http:
            raise RuntimeError("Cannot delete webhook without HTTPClient")

        await self._http.delete_webhook(self.id, reason=reason)
