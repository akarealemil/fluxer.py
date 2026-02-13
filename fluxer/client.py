from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine

from .enums import Intents
from .gateway import Gateway
from .http import HTTPClient
from .models import Channel, Guild, Message, User, Webhook

log = logging.getLogger(__name__)

# Type alias for event handlers
EventHandler = Callable[..., Coroutine[Any, Any, None]]


class Client:
    """Low-level client that connects to Fluxer and dispatches events.

    This gives you full control over the gateway lifecycle.
    For most bots, use the Bot subclass instead.
    """

    def __init__(self, *, intents: Intents = Intents.default()) -> None:
        self.intents = intents
        self._http: HTTPClient | None = None
        self._gateway: Gateway | None = None
        self._event_handlers: dict[str, list[EventHandler]] = {}
        self._user: User | None = None
        self._guilds: dict[str, Guild] = {}
        self._channels: dict[str, Channel] = {}
        self._closed: bool = False

    @property
    def user(self) -> User | None:
        """The bot user, available after the READY event."""
        return self._user

    @property
    def guilds(self) -> list[Guild]:
        """List of guilds the bot is in (populated from READY + GUILD_CREATE)."""
        return list(self._guilds.values())

    # =========================================================================
    # Event registration
    # =========================================================================

    def event(self, func: EventHandler) -> EventHandler:
        """Decorator to register an event handler.

        The function name determines the event:
            @bot.event
            async def on_message(message):
                ...

        Supported events (mapped from gateway dispatch names):
            on_ready       -> READY
            on_message      -> MESSAGE_CREATE
            on_message_edit -> MESSAGE_UPDATE
            on_message_delete -> MESSAGE_DELETE
            on_guild_join   -> GUILD_CREATE
            on_guild_remove -> GUILD_DELETE
            on_member_join  -> GUILD_MEMBER_ADD
            on_member_remove -> GUILD_MEMBER_REMOVE
            ... and any other gateway event as on_{lowercase_name}
        """
        event_name = func.__name__
        if not event_name.startswith("on_"):
            raise ValueError(f"Event handler must start with 'on_', got '{event_name}'")

        if event_name not in self._event_handlers:
            self._event_handlers[event_name] = []
        self._event_handlers[event_name].append(func)
        return func

    def on(self, event_name: str) -> Callable[[EventHandler], EventHandler]:
        """Decorator to register an event handler with an explicit name.

        Usage:
            @bot.on("message")
            async def handle_msg(message):
                ...
        """

        def decorator(func: EventHandler) -> EventHandler:
            key = f"on_{event_name}"
            if key not in self._event_handlers:
                self._event_handlers[key] = []
            self._event_handlers[key].append(func)
            return func

        return decorator

    # =========================================================================
    # Event dispatching
    # =========================================================================

    async def _dispatch(self, event_name: str, data: Any) -> None:
        """Called by the Gateway when a dispatch event is received.

        This method:
        1. Parses the raw data into model objects
        2. Updates internal caches
        3. Fires matching user event handlers
        """
        # Map gateway event names to handler names and parse data
        match event_name:
            case "READY":
                self._user = User.from_data(data["user"], self._http)
                # Process guilds from READY
                for guild_data in data.get("guilds", []):
                    guild = Guild.from_data(guild_data, self._http)
                    self._guilds[guild.id] = guild
                await self._fire("on_ready")

            case "MESSAGE_CREATE":
                message = self._parse_message(data)
                await self._fire("on_message", message)

            case "MESSAGE_UPDATE":
                message = self._parse_message(data)
                await self._fire("on_message_edit", message)

            case "MESSAGE_DELETE":
                await self._fire("on_message_delete", data)

            case "GUILD_CREATE":
                guild = Guild.from_data(data, self._http)
                self._guilds[guild.id] = guild
                # Cache channels from guild
                for ch_data in data.get("channels", []):
                    ch = Channel.from_data(ch_data, self._http)
                    self._channels[ch.id] = ch
                await self._fire("on_guild_join", guild)

            case "GUILD_DELETE":
                guild_id = data.get("id", "")
                guild = self._guilds.pop(guild_id, None)
                await self._fire("on_guild_remove", guild or data)

            case "GUILD_MEMBER_ADD":
                await self._fire("on_member_join", data)

            case "GUILD_MEMBER_REMOVE":
                await self._fire("on_member_remove", data)

            case "CHANNEL_CREATE":
                channel = Channel.from_data(data, self._http)
                self._channels[channel.id] = channel
                await self._fire("on_channel_create", channel)

            case "CHANNEL_UPDATE":
                channel = Channel.from_data(data, self._http)
                self._channels[channel.id] = channel
                await self._fire("on_channel_update", channel)

            case "CHANNEL_DELETE":
                channel = Channel.from_data(data, self._http)
                self._channels.pop(channel.id, None)
                await self._fire("on_channel_delete", channel)

            case "RESUMED":
                await self._fire("on_resumed")

            case _:
                # Unknown/unhandled event — fire a generic handler
                handler_name = f"on_{event_name.lower()}"
                await self._fire(handler_name, data)

    def _parse_message(self, data: dict[str, Any]) -> Message:
        """Parse message data and attach cached channel reference."""
        msg = Message.from_data(data, self._http)
        # Attach cached channel
        cached_channel = self._channels.get(msg.channel_id)
        if cached_channel:
            msg._channel = cached_channel
        return msg

    async def _fire(self, event_name: str, *args: Any) -> None:
        """Fire all registered handlers for an event."""
        handlers = self._event_handlers.get(event_name, [])
        for handler in handlers:
            try:
                await handler(*args)
            except Exception:
                log.exception("Error in event handler '%s'", event_name)

    # =========================================================================
    # HTTP convenience methods
    # =========================================================================

    async def fetch_channel(self, channel_id: str) -> Channel:
        """Fetch a channel from the API (not cache)."""
        assert self._http is not None
        data = await self._http.get_channel(channel_id)
        ch = Channel.from_data(data, self._http)
        self._channels[ch.id] = ch
        return ch

    async def fetch_guild(self, guild_id: str) -> Guild:
        """Fetch a guild from the API."""
        assert self._http is not None
        data = await self._http.get_guild(guild_id)
        guild = Guild.from_data(data, self._http)
        self._guilds[guild.id] = guild
        return guild

    async def fetch_user(self, user_id: str) -> User:
        """Fetch a user from the API."""
        assert self._http is not None
        data = await self._http.get_user(user_id)
        return User.from_data(data, self._http)

    async def fetch_webhook(self, webhook_id: str) -> Webhook:
        """Fetch a webhook from the API."""
        assert self._http is not None
        data = await self._http.get_webhook(webhook_id)
        return Webhook.from_data(data, self._http)

    async def fetch_channel_webhooks(self, channel_id: str) -> list[Webhook]:
        """Fetch all webhooks for a channel."""
        assert self._http is not None
        data = await self._http.get_channel_webhooks(channel_id)
        return [Webhook.from_data(w, self._http) for w in data]

    async def fetch_guild_webhooks(self, guild_id: str) -> list[Webhook]:
        """Fetch all webhooks for a guild."""
        assert self._http is not None
        data = await self._http.get_guild_webhooks(guild_id)
        return [Webhook.from_data(w, self._http) for w in data]

    async def create_webhook(
        self, channel_id: str, *, name: str, avatar: str | None = None
    ) -> Webhook:
        """Create a webhook in a channel."""
        assert self._http is not None
        data = await self._http.create_webhook(channel_id, name=name, avatar=avatar)
        return Webhook.from_data(data, self._http)

    # =========================================================================
    # Connection lifecycle
    # =========================================================================

    async def start(self, token: str) -> None:
        """Connect to Fluxer and start receiving events (async version).

        Use this if you're managing your own event loop.
        """
        self._http = HTTPClient(token)
        self._gateway = Gateway(
            http_client=self._http,
            token=token,
            intents=self.intents,
            dispatch=self._dispatch,
        )

        try:
            await self._gateway.connect()
        finally:
            await self.close()

    async def close(self) -> None:
        """Disconnect from the gateway and clean up resources."""
        self._closed = True
        if self._gateway:
            await self._gateway.close()
        if self._http:
            await self._http.close()

    def run(self, token: str) -> None:
        """Blocking call that connects to Fluxer and runs the bot.

        This is the simplest way to start your bot:
            bot.run("your_token_here")

        It creates an event loop, calls start(), and handles cleanup.
        """

        async def _runner() -> None:
            try:
                await self.start(token)
            except KeyboardInterrupt:
                pass
            finally:
                if not self._closed:
                    await self.close()

        try:
            asyncio.run(_runner())
        except KeyboardInterrupt:
            log.info("Bot stopped by KeyboardInterrupt")


class Bot(Client):
    """Extended Client with common bot conveniences.

    Adds prefix command support and other bot-specific features.
    This is the recommended class for most bot use cases.
    """

    def __init__(
        self,
        *,
        command_prefix: str = "!",
        intents: Intents = Intents.default(),
    ) -> None:
        super().__init__(intents=intents)
        self.command_prefix = command_prefix
        self._commands: dict[str, EventHandler] = {}

        # Auto-register the command dispatcher
        @self.event
        async def on_message(message: Message) -> None:
            await self._process_commands(message)

    def command(
        self, name: str | None = None
    ) -> Callable[[EventHandler], EventHandler]:
        """Decorator to register a prefix command.

        Usage:
            @bot.command()
            async def ping(message):
                await message.reply("Pong!")

            @bot.command(name="hello")
            async def greet(message):
                await message.reply(f"Hello, {message.author}!")
        """

        def decorator(func: EventHandler) -> EventHandler:
            cmd_name = name or func.__name__
            self._commands[cmd_name] = func
            return func

        return decorator

    async def _process_commands(self, message: Message) -> None:
        """Check if a message matches a registered command and invoke it."""
        if message.author.bot:
            return
        if not message.content.startswith(self.command_prefix):
            return

        # Parse command name and args
        content = message.content[len(self.command_prefix) :]
        parts = content.split(maxsplit=1)
        if not parts:
            return

        cmd_name = parts[0].lower()
        # args_str = parts[1] if len(parts) > 1 else ""

        handler = self._commands.get(cmd_name)
        if handler:
            try:
                await handler(message)
            except Exception:
                log.exception("Error in command '%s'", cmd_name)
