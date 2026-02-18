from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from .errors import http_exception_from_status

log = logging.getLogger(__name__)

BASE_URL = "https://api.fluxer.app/v1"


def _get_user_agent() -> str:
    """Get the user agent string with the current version."""
    from . import __version__

    return f"fluxer.py/{__version__} (https://github.com/akarealemil/fluxer.py)"


class Route:
    """Represents an API route. Used for rate limit bucketing.

    Usage:
        route = Route("GET", "/channels/{channel_id}/messages", channel_id="123")
        # route.url = "https://api.fluxer.app/v1/channels/123/messages"
        # route.bucket = "GET /channels/{channel_id}/messages"
    """

    def __init__(self, method: str, path: str, **params: Any) -> None:
        self.method = method
        self.path = path
        # Convert all parameters to strings for URL formatting (handles int IDs)
        self.params = {k: str(v) for k, v in params.items()}
        self.url = BASE_URL + path.format(**self.params)

        # Rate limit bucket key: method + path template + major params
        # Major params (channel_id, guild_id) get their own buckets
        self.bucket = f"{method} {path}"
        for key in ("channel_id", "guild_id", "webhook_id"):
            if key in self.params:
                self.bucket += f":{self.params[key]}"


class RateLimiter:
    """Per-route rate limit handler using Fluxer's response headers.

    Fluxer returns rate limit info via HTTP headers (same pattern as Discord):
        X-RateLimit-Limit: max requests in window
        X-RateLimit-Remaining: requests left
        X-RateLimit-Reset: Unix timestamp when the limit resets
        X-RateLimit-Reset-After: seconds until reset
        X-RateLimit-Bucket: opaque bucket identifier
    """

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._reset_times: dict[str, float] = {}
        self._global_lock = asyncio.Event()
        self._global_lock.set()  # Not locked initially

    def _get_lock(self, bucket: str) -> asyncio.Lock:
        if bucket not in self._locks:
            self._locks[bucket] = asyncio.Lock()
        return self._locks[bucket]

    async def acquire(self, bucket: str) -> None:
        """Wait if this bucket or global rate limit is active."""
        # Wait for global rate limit to clear
        await self._global_lock.wait()

        lock = self._get_lock(bucket)
        await lock.acquire()

        # Check if we need to wait for this bucket
        reset_at = self._reset_times.get(bucket)
        if reset_at is not None:
            now = asyncio.get_event_loop().time()
            if now < reset_at:
                delay = reset_at - now
                log.debug("Rate limited on bucket %s, waiting %.2fs", bucket, delay)
                await asyncio.sleep(delay)

    def release(self, bucket: str, headers: dict[str, str]) -> None:
        """Update rate limit state from response headers and release the lock."""
        remaining = headers.get("X-RateLimit-Remaining")
        reset_after = headers.get("X-RateLimit-Reset-After")

        if remaining is not None and int(remaining) == 0 and reset_after is not None:
            delay = float(reset_after)
            self._reset_times[bucket] = asyncio.get_event_loop().time() + delay
            log.debug("Bucket %s exhausted, reset in %.2fs", bucket, delay)
        else:
            self._reset_times.pop(bucket, None)

        lock = self._get_lock(bucket)
        if lock.locked():
            lock.release()

    def set_global(self, retry_after: float) -> None:
        """Activate a global rate limit."""
        self._global_lock.clear()
        log.warning("Global rate limit hit, pausing for %.2fs", retry_after)

        async def _unlock() -> None:
            await asyncio.sleep(retry_after)
            self._global_lock.set()

        asyncio.ensure_future(_unlock())


class HTTPClient:
    """Async HTTP client for the Fluxer REST API.

    Usage:
        async with HTTPClient(token) as http:
            data = await http.request(Route("GET", "/users/@me"))
    """

    def __init__(self, token: str, *, is_bot: bool = True) -> None:
        self.token = token
        self.is_bot = is_bot
        self._session: aiohttp.ClientSession | None = None
        self._rate_limiter = RateLimiter()

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            # Use "Bot" prefix for bot tokens, plain token for user tokens
            auth_header = f"Bot {self.token}" if self.is_bot else self.token
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": auth_header,
                    "User-Agent": _get_user_agent(),
                }
            )
        return self._session

    async def close(self) -> None:
        """Close the underlying HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def __aenter__(self) -> HTTPClient:
        await self._ensure_session()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def request(
        self,
        route: Route,
        *,
        json: Any = None,
        data: aiohttp.FormData | None = None,
        params: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> Any:
        """Make an authenticated request to the Fluxer API.

        Handles rate limiting, retries on 429/5xx, and error mapping.

        Returns:
            Parsed JSON response, or None for 204 No Content.
        """
        session = await self._ensure_session()

        headers: dict[str, str] = {}
        if reason:
            headers["X-Audit-Log-Reason"] = reason
        if json is not None:
            headers["Content-Type"] = "application/json"

        for attempt in range(5):  # Max retries
            await self._rate_limiter.acquire(route.bucket)

            try:
                async with session.request(
                    route.method,
                    route.url,
                    json=json,
                    data=data,
                    params=params,
                    headers=headers,
                ) as resp:
                    resp_headers = {k: v for k, v in resp.headers.items()}
                    self._rate_limiter.release(route.bucket, resp_headers)

                    # Success
                    if 200 <= resp.status < 300:
                        if resp.status == 204:
                            return None
                        return await resp.json()

                    # Rate limited
                    if resp.status == 429:
                        body = await resp.json()
                        retry_after = body.get("retry_after", 1.0)
                        is_global = body.get("global", False)

                        if is_global:
                            self._rate_limiter.set_global(retry_after)
                        else:
                            log.warning(
                                "Rate limited on %s, retry in %.2fs (attempt %d)",
                                route.url,
                                retry_after,
                                attempt + 1,
                            )
                            await asyncio.sleep(retry_after)
                        continue

                    # Server error — retry
                    if resp.status >= 500:
                        log.warning(
                            "Server error %d on %s, retrying (attempt %d)",
                            resp.status,
                            route.url,
                            attempt + 1,
                        )
                        await asyncio.sleep(1 + attempt)
                        continue

                    # Client error — raise
                    body = await resp.json()
                    raise http_exception_from_status(
                        status=resp.status,
                        code=body.get("code", "UNKNOWN"),
                        message=body.get("message", "Unknown error"),
                        errors=body.get("errors"),
                        retry_after=body.get("retry_after", 0.0),
                    )

            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                if attempt < 4:
                    log.warning(
                        "Connection error: %s, retrying (attempt %d)", exc, attempt + 1
                    )
                    await asyncio.sleep(1 + attempt)
                    continue
                raise

        raise RuntimeError(f"Failed after 5 attempts: {route.method} {route.url}")

    # =========================================================================
    # Convenience methods for common endpoints
    # =========================================================================

    # -- Gateway --
    async def get_gateway(self) -> dict[str, Any]:
        """GET /gateway/bot — get the WebSocket URL.

        Note: Fluxer's /gateway endpoint returns 404 for bots.
        This method uses /gateway/bot instead (bot tokens only).
        """
        return await self.get_gateway_bot()

    async def get_gateway_bot(self) -> dict[str, Any]:
        """GET /gateway/bot — get gateway URL + sharding info."""
        return await self.request(Route("GET", "/gateway/bot"))

    # -- Users --
    async def get_current_user(self) -> dict[str, Any]:
        """GET /users/@me"""
        return await self.request(Route("GET", "/users/@me"))

    async def get_user(self, user_id: int | str) -> dict[str, Any]:
        """GET /users/{user_id}"""
        return await self.request(Route("GET", "/users/{user_id}", user_id=user_id))

    async def get_user_profile(
        self, user_id: int | str, *, guild_id: int | str | None = None
    ) -> dict[str, Any]:
        """GET /users/{user_id}/profile — Get a user's full profile.

        This returns additional profile information like bio, pronouns, banner, etc.
        that is not included in the basic user object.

        Args:
            user_id: The user ID to fetch
            guild_id: Optional guild ID for guild-specific profile data

        Returns:
            Profile object containing:
            - user: Basic user object
            - user_profile: Profile data (bio, pronouns, banner, etc.)
            - premium_type, premium_since, premium_lifetime_sequence
        """
        route = Route("GET", "/users/{user_id}/profile", user_id=user_id)
        params = {"guild_id": str(guild_id)} if guild_id else None
        return await self.request(route, params=params)

    async def get_current_user_guilds(self) -> list[dict[str, Any]]:
        """GET /users/@me/guilds - get guilds the current user is in"""
        return await self.request(Route("GET", "/users/@me/guilds"))

    # -- Channels --
    async def get_channel(self, channel_id: int | str) -> dict[str, Any]:
        """GET /channels/{channel_id}"""
        return await self.request(
            Route("GET", "/channels/{channel_id}", channel_id=channel_id)
        )

    # -- Messages --
    async def send_message(
        self,
        channel_id: int | str,
        *,
        content: str | None = None,
        embeds: list[dict[str, Any]] | None = None,
        files: list[Any] | None = None,
    ) -> dict[str, Any]:
        """POST /channels/{channel_id}/messages"""
        route = Route("POST", "/channels/{channel_id}/messages", channel_id=channel_id)

        payload: dict[str, Any] = {}
        if content is not None:
            payload["content"] = content
        if embeds is not None:
            payload["embeds"] = embeds

        if files:
            # Use multipart form data for file uploads
            form = aiohttp.FormData()
            import json as json_mod

            form.add_field(
                "payload_json", json_mod.dumps(payload), content_type="application/json"
            )
            for i, file in enumerate(files):
                form.add_field(f"files[{i}]", file["data"], filename=file["filename"])
            return await self.request(route, data=form)

        return await self.request(route, json=payload)

    async def get_messages(
        self,
        channel_id: int | str,
        *,
        limit: int = 50,
        before: int | str | None = None,
        after: int | str | None = None,
    ) -> list[dict[str, Any]]:
        """GET /channels/{channel_id}/messages"""
        params: dict[str, Any] = {"limit": limit}
        if before:
            params["before"] = before
        if after:
            params["after"] = after

        route = Route("GET", "/channels/{channel_id}/messages", channel_id=channel_id)
        return await self.request(route, params=params)

    async def edit_message(
        self,
        channel_id: int | str,
        message_id: int | str,
        *,
        content: str | None = None,
        embeds: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """PATCH /channels/{channel_id}/messages/{message_id}"""
        route = Route(
            "PATCH",
            "/channels/{channel_id}/messages/{message_id}",
            channel_id=channel_id,
            message_id=message_id,
        )
        payload: dict[str, Any] = {}
        if content is not None:
            payload["content"] = content
        if embeds is not None:
            payload["embeds"] = embeds
        return await self.request(route, json=payload)

    async def delete_message(self, channel_id: int | str, message_id: int | str) -> None:
        """DELETE /channels/{channel_id}/messages/{message_id}"""
        route = Route(
            "DELETE",
            "/channels/{channel_id}/messages/{message_id}",
            channel_id=channel_id,
            message_id=message_id,
        )
        await self.request(route)
        
    async def add_reaction(self, channel_id: int | str, message_id: int | str, emoji: str) -> None:
        """PUT /channels/{channel_id}/messages/{message_id}/reactions/{emoji}/@me"""
        route = Route(
            "PUT", "/channels/{channel_id}/messages/{message_id}/reactions/{emoji}/@me",
            channel_id=channel_id,
            message_id=message_id,
            emoji=emoji
        )
        await self.request(route)

    # -- Guilds --
    async def get_guild(self, guild_id: int | str) -> dict[str, Any]:
        """GET /guilds/{guild_id}"""
        return await self.request(Route("GET", "/guilds/{guild_id}", guild_id=guild_id))

    async def get_guild_channels(self, guild_id: int | str) -> list[dict[str, Any]]:
        """GET /guilds/{guild_id}/channels"""
        return await self.request(
            Route("GET", "/guilds/{guild_id}/channels", guild_id=guild_id)
        )

    async def get_guild_member(
        self, guild_id: int | str, user_id: int | str
    ) -> dict[str, Any]:
        """GET /guilds/{guild_id}/members/{user_id} — Get a specific guild member."""
        return await self.request(
            Route(
                "GET",
                "/guilds/{guild_id}/members/{user_id}",
                guild_id=guild_id,
                user_id=user_id,
            )
        )

    async def get_guild_members(
        self, guild_id: int | str, *, limit: int = 100, after: int | str | None = None
    ) -> list[dict[str, Any]]:
        """GET /guilds/{guild_id}/members — List guild members."""
        params: dict[str, Any] = {"limit": limit}
        if after:
            params["after"] = after

        return await self.request(
            Route("GET", "/guilds/{guild_id}/members", guild_id=guild_id), params=params
        )

    async def create_guild(
        self,
        *,
        name: str,
        icon: bytes | None = None,
    ) -> dict[str, Any]:
        """POST /guilds — Create a new guild.

        Args:
            name: Guild name (2-100 characters)
            icon: Icon image data (PNG/JPG/GIF)

        Returns:
            Guild object
        """
        import base64

        payload: dict[str, Any] = {"name": name}

        if icon:
            # Convert bytes to base64 data URI
            image_data = base64.b64encode(icon).decode("ascii")
            # Detect image format from header
            if icon.startswith(b"\x89PNG"):
                mime_type = "image/png"
            elif icon.startswith(b"\xff\xd8\xff"):
                mime_type = "image/jpeg"
            elif icon.startswith(b"GIF89a") or icon.startswith(b"GIF87a"):
                mime_type = "image/gif"
            else:
                mime_type = "image/png"  # Default

            payload["icon"] = f"data:{mime_type};base64,{image_data}"

        return await self.request(Route("POST", "/guilds"), json=payload)

    async def delete_guild(self, guild_id: int | str) -> None:
        """DELETE /guilds/{guild_id}"""
        await self.request(Route("DELETE", "/guilds/{guild_id}", guild_id=guild_id))

    async def modify_guild(
        self,
        guild_id: int | str,
        *,
        name: str | None = None,
        icon: bytes | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """PATCH /guilds/{guild_id} — Modify guild settings."""
        import base64

        payload: dict[str, Any] = {}

        if name is not None:
            payload["name"] = name

        if icon is not None:
            image_data = base64.b64encode(icon).decode("ascii")
            if icon.startswith(b"\x89PNG"):
                mime_type = "image/png"
            elif icon.startswith(b"\xff\xd8\xff"):
                mime_type = "image/jpeg"
            else:
                mime_type = "image/png"

            payload["icon"] = f"data:{mime_type};base64,{image_data}"

        payload.update(kwargs)

        return await self.request(
            Route("PATCH", "/guilds/{guild_id}", guild_id=guild_id), json=payload
        )

    # -- Roles --
    async def get_guild_roles(self, guild_id: int | str) -> list[dict[str, Any]]:
        """GET /guilds/{guild_id}/roles"""
        return await self.request(
            Route("GET", "/guilds/{guild_id}/roles", guild_id=guild_id)
        )

    async def create_guild_role(
        self,
        guild_id: int | str,
        *,
        name: str | None = None,
        permissions: int | None = None,
        color: int = 0,
        hoist: bool = False,
        mentionable: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """POST /guilds/{guild_id}/roles — Create a new role."""
        payload: dict[str, Any] = {
            "color": color,
            "hoist": hoist,
            "mentionable": mentionable,
        }

        if name is not None:
            payload["name"] = name
        if permissions is not None:
            payload["permissions"] = str(permissions)

        payload.update(kwargs)

        return await self.request(
            Route("POST", "/guilds/{guild_id}/roles", guild_id=guild_id), json=payload
        )

    async def modify_guild_role(
        self,
        guild_id: int | str,
        role_id: int | str,
        *,
        name: str | None = None,
        permissions: int | None = None,
        color: int | None = None,
        hoist: bool | None = None,
        mentionable: bool | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """PATCH /guilds/{guild_id}/roles/{role_id}"""
        payload: dict[str, Any] = {}

        if name is not None:
            payload["name"] = name
        if permissions is not None:
            payload["permissions"] = str(permissions)
        if color is not None:
            payload["color"] = color
        if hoist is not None:
            payload["hoist"] = hoist
        if mentionable is not None:
            payload["mentionable"] = mentionable

        payload.update(kwargs)

        return await self.request(
            Route(
                "PATCH",
                "/guilds/{guild_id}/roles/{role_id}",
                guild_id=guild_id,
                role_id=role_id,
            ),
            json=payload,
        )

    async def delete_guild_role(self, guild_id: int | str, role_id: int | str) -> None:
        """DELETE /guilds/{guild_id}/roles/{role_id}"""
        await self.request(
            Route(
                "DELETE",
                "/guilds/{guild_id}/roles/{role_id}",
                guild_id=guild_id,
                role_id=role_id,
            )
        )

    # -- Channels (create/modify) --
    async def create_guild_channel(
        self,
        guild_id: int | str,
        *,
        name: str,
        type: int = 0,
        topic: str | None = None,
        bitrate: int | None = None,
        user_limit: int | None = None,
        position: int | None = None,
        parent_id: int | str | None = None,
        nsfw: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """POST /guilds/{guild_id}/channels — Create a channel.

        Args:
            guild_id: Guild to create channel in
            name: Channel name
            type: Channel type (0=text, 2=voice, 4=category)
            topic: Channel topic (text channels)
            bitrate: Bitrate (voice channels)
            user_limit: User limit (voice channels)
            position: Channel position
            parent_id: Parent category ID
            nsfw: Whether the channel is NSFW

        Returns:
            Channel object
        """
        payload: dict[str, Any] = {
            "name": name,
            "type": type,
            "nsfw": nsfw,
        }

        if topic is not None:
            payload["topic"] = topic
        if bitrate is not None:
            payload["bitrate"] = bitrate
        if user_limit is not None:
            payload["user_limit"] = user_limit
        if position is not None:
            payload["position"] = position
        if parent_id is not None:
            payload["parent_id"] = parent_id

        payload.update(kwargs)

        return await self.request(
            Route("POST", "/guilds/{guild_id}/channels", guild_id=guild_id),
            json=payload,
        )

    async def modify_channel(
        self,
        channel_id: int | str,
        *,
        name: str | None = None,
        type: int | None = None,
        topic: str | None = None,
        position: int | None = None,
        parent_id: int | str | None = None,
        nsfw: bool | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """PATCH /channels/{channel_id}"""
        payload: dict[str, Any] = {}

        if name is not None:
            payload["name"] = name
        if type is not None:
            payload["type"] = type
        if topic is not None:
            payload["topic"] = topic
        if position is not None:
            payload["position"] = position
        if parent_id is not None:
            payload["parent_id"] = parent_id
        if nsfw is not None:
            payload["nsfw"] = nsfw

        payload.update(kwargs)

        return await self.request(
            Route("PATCH", "/channels/{channel_id}", channel_id=channel_id),
            json=payload,
        )

    async def delete_channel(self, channel_id: int | str) -> None:
        """DELETE /channels/{channel_id}"""
        await self.request(
            Route("DELETE", "/channels/{channel_id}", channel_id=channel_id)
        )

    async def edit_channel_permissions(
        self,
        channel_id: int | str,
        overwrite_id: int | str,
        *,
        allow: int | str | None = None,
        deny: int | str | None = None,
        type: int = 0,
        **kwargs: Any,
    ) -> None:
        """PUT /channels/{channel_id}/permissions/{overwrite_id} — Edit channel permission overwrites.

        Args:
            channel_id: Channel ID
            overwrite_id: Role or user ID
            allow: Allowed permissions (bitwise)
            deny: Denied permissions (bitwise)
            type: 0 for role, 1 for member

        Returns:
            None (204 No Content)
        """
        payload: dict[str, Any] = {"type": type}

        if allow is not None:
            payload["allow"] = str(allow)
        if deny is not None:
            payload["deny"] = str(deny)

        payload.update(kwargs)

        await self.request(
            Route(
                "PUT",
                "/channels/{channel_id}/permissions/{overwrite_id}",
                channel_id=channel_id,
                overwrite_id=overwrite_id,
            ),
            json=payload,
        )

    # -- User Profile --
    async def modify_current_user(
        self,
        *,
        username: str | None = None,
        avatar: bytes | None = None,
        banner: bytes | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """PATCH /users/@me — Modify the current user's profile.

        Args:
            username: New username
            avatar: Avatar image data (PNG/JPG/GIF)
            banner: Banner image data (PNG/JPG/GIF)

        Returns:
            Updated user object
        """
        import base64

        payload: dict[str, Any] = {}

        if username is not None:
            payload["username"] = username

        if avatar is not None:
            image_data = base64.b64encode(avatar).decode("ascii")
            if avatar.startswith(b"\x89PNG"):
                mime_type = "image/png"
            elif avatar.startswith(b"\xff\xd8\xff"):
                mime_type = "image/jpeg"
            elif avatar.startswith(b"GIF89a") or avatar.startswith(b"GIF87a"):
                mime_type = "image/gif"
            else:
                mime_type = "image/png"

            payload["avatar"] = f"data:{mime_type};base64,{image_data}"

        if banner is not None:
            image_data = base64.b64encode(banner).decode("ascii")
            if banner.startswith(b"\x89PNG"):
                mime_type = "image/png"
            elif banner.startswith(b"\xff\xd8\xff"):
                mime_type = "image/jpeg"
            elif banner.startswith(b"GIF89a") or banner.startswith(b"GIF87a"):
                mime_type = "image/gif"
            else:
                mime_type = "image/png"

            payload["banner"] = f"data:{mime_type};base64,{image_data}"

        payload.update(kwargs)

        return await self.request(Route("PATCH", "/users/@me"), json=payload)

    # -- Emojis --
    async def get_guild_emojis(self, guild_id: int | str) -> list[dict[str, Any]]:
        """GET /guilds/{guild_id}/emojis — Get all emojis for a guild.

        Returns:
            List of emoji objects
        """
        return await self.request(
            Route("GET", "/guilds/{guild_id}/emojis", guild_id=guild_id)
        )

    async def get_guild_emoji(self, guild_id: int | str, emoji_id: int | str) -> dict[str, Any]:
        """GET /guilds/{guild_id}/emojis/{emoji_id} — Get a specific emoji.

        Returns:
            Emoji object
        """
        return await self.request(
            Route(
                "GET",
                "/guilds/{guild_id}/emojis/{emoji_id}",
                guild_id=guild_id,
                emoji_id=emoji_id,
            )
        )

    async def create_guild_emoji(
        self,
        guild_id: int | str,
        *,
        name: str,
        image: bytes,
        roles: list[int | str] | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """POST /guilds/{guild_id}/emojis — Create a new emoji.

        Args:
            guild_id: Guild ID
            name: Emoji name
            image: Image data (PNG/JPG/GIF)
            roles: List of role IDs that can use this emoji (optional)
            reason: Reason for creation (audit log)

        Returns:
            Emoji object
        """
        import base64

        # Convert bytes to base64 data URI
        image_data = base64.b64encode(image).decode("ascii")

        # Detect image format from header
        if image.startswith(b"\x89PNG"):
            mime_type = "image/png"
        elif image.startswith(b"\xff\xd8\xff"):
            mime_type = "image/jpeg"
        elif image.startswith(b"GIF89a") or image.startswith(b"GIF87a"):
            mime_type = "image/gif"
        else:
            mime_type = "image/png"  # Default

        payload: dict[str, Any] = {
            "name": name,
            "image": f"data:{mime_type};base64,{image_data}",
        }

        if roles is not None:
            payload["roles"] = [str(role_id) for role_id in roles]

        return await self.request(
            Route("POST", "/guilds/{guild_id}/emojis", guild_id=guild_id),
            json=payload,
            reason=reason,
        )

    async def delete_guild_emoji(
        self,
        guild_id: int | str,
        emoji_id: int | str,
        *,
        reason: str | None = None,
    ) -> None:
        """DELETE /guilds/{guild_id}/emojis/{emoji_id} — Delete an emoji.

        Args:
            guild_id: Guild ID
            emoji_id: Emoji ID
            reason: Reason for deletion (audit log)
        """
        await self.request(
            Route(
                "DELETE",
                "/guilds/{guild_id}/emojis/{emoji_id}",
                guild_id=guild_id,
                emoji_id=emoji_id,
            ),
            reason=reason,
        )

    # ~~ Webhooks ~
    async def get_guild_webhooks(self, guild_id: int | str) -> list[dict[str, Any]]:
        """GET /guilds/{guild_id}/webhooks"""
        return await self.request(
            Route("GET", "/guilds/{guild_id}/webhooks", guild_id=guild_id)
        )

    async def get_channel_webhooks(self, channel_id: int | str) -> list[dict[str, Any]]:
        """GET /channels/{channel_id}/webhooks"""
        return await self.request(
            Route("GET", "/channels/{channel_id}/webhooks", channel_id=channel_id)
        )

    async def create_webhook(
        self,
        channel_id: int | str,
        *,
        name: str,
        avatar: str | None = None,
    ) -> dict[str, Any]:
        """POST /channels/{channel_id}/webhooks"""
        payload: dict[str, Any] = {"name": name}
        if avatar is not None:
            payload["avatar"] = avatar
        return await self.request(
            Route("POST", "/channels/{channel_id}/webhooks", channel_id=channel_id),
            json=payload,
        )

    async def get_webhook(self, webhook_id: int | str) -> dict[str, Any]:
        """GET /webhooks/{webhook_id}"""
        return await self.request(
            Route("GET", "/webhooks/{webhook_id}", webhook_id=webhook_id)
        )

    async def get_webhook_with_token(
        self, webhook_id: int | str, token: str
    ) -> dict[str, Any]:
        """GET /webhooks/{webhook_id}/{token}"""
        return await self.request(
            Route(
                "GET",
                "/webhooks/{webhook_id}/{token}",
                webhook_id=webhook_id,
                token=token,
            )
        )

    async def modify_webhook(
        self,
        webhook_id: int | str,
        *,
        name: str | None = None,
        avatar: str | None = None,
        channel_id: int | str | None = None,
    ) -> dict[str, Any]:
        """PATCH /webhooks/{webhook_id}"""
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if avatar is not None:
            payload["avatar"] = avatar
        if channel_id is not None:
            payload["channel_id"] = channel_id
        return await self.request(
            Route("PATCH", "/webhooks/{webhook_id}", webhook_id=webhook_id),
            json=payload,
        )

    async def modify_webhook_with_token(
        self,
        webhook_id: int | str,
        token: str,
        *,
        name: str | None = None,
        avatar: str | None = None,
        channel_id: int | str | None = None,
    ) -> dict[str, Any]:
        """PATCH /webhooks/{webhook_id}/{token}"""
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if avatar is not None:
            payload["avatar"] = avatar
        if channel_id is not None:
            payload["channel_id"] = channel_id
        return await self.request(
            Route(
                "PATCH",
                "/webhooks/{webhook_id}/{token}",
                webhook_id=webhook_id,
                token=token,
            ),
            json=payload,
        )

    async def delete_webhook(
        self, webhook_id: int | str, *, reason: str | None = None
    ) -> None:
        """DELETE /webhooks/{webhook_id}"""
        await self.request(
            Route("DELETE", "/webhooks/{webhook_id}", webhook_id=webhook_id),
            reason=reason,
        )

    async def delete_webhook_with_token(self, webhook_id: int | str, token: str) -> None:
        """DELETE /webhooks/{webhook_id}/{token}"""
        await self.request(
            Route(
                "DELETE",
                "/webhooks/{webhook_id}/{token}",
                webhook_id=webhook_id,
                token=token,
            ),
        )

    async def execute_webhook(
        self,
        webhook_id: int | str,
        token: str,
        *,
        content: str | None = None,
        embeds: list[dict[str, Any]] | None = None,
        username: str | None = None,
        avatar_url: str | None = None,
        wait: bool = False,
    ) -> dict[str, Any] | None:
        """POST /webhooks/{webhook_id}/{token}"""
        payload: dict[str, Any] = {}
        if content is not None:
            payload["content"] = content
        if embeds is not None:
            payload["embeds"] = embeds
        if username is not None:
            payload["username"] = username
        if avatar_url is not None:
            payload["avatar_url"] = avatar_url
        params = {"wait": "true"} if wait else None
        return await self.request(
            Route(
                "POST",
                "/webhooks/{webhook_id}/{token}",
                webhook_id=webhook_id,
                token=token,
            ),
            json=payload,
            params=params,
        )
