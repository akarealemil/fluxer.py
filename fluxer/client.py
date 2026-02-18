from __future__ import annotations

import asyncio
import importlib
import importlib.util
import inspect
import logging
import sys
from pathlib import Path
from typing import Any, Callable, Coroutine

from .enums import Intents
from .gateway import Gateway
from .http import HTTPClient
from .models import Channel, Guild, Message, User, UserProfile, Webhook

log = logging.getLogger(__name__)

# Type alias for event handlers
EventHandler = Callable[..., Coroutine[Any, Any, None]]


class Client:
    """Low-level client that connects to Fluxer and dispatches events.

    This gives you full control over the gateway lifecycle.
    For most bots, use the Bot subclass instead.

    Args:
        intents: Gateway intents to request (default: Intents.default())
        api_url: Base URL for the Fluxer API (default: https://api.fluxer.app/v1)
                 Use this to connect to self-hosted Fluxer instances
    """

    def __init__(
        self,
        *,
        intents: Intents = Intents.default(),
        api_url: str | None = None
    ) -> None:
        self.intents = intents
        self.api_url = api_url
        self._http: HTTPClient | None = None
        self._gateway: Gateway | None = None
        self._event_handlers: dict[str, list[EventHandler]] = {}
        self._user: User | None = None
        self._guilds: dict[int, Guild] = {}
        self._channels: dict[int, Channel] = {}
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
                guild_id = int(data["id"])
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

            case "MESSAGE_REACTION_ADD":
                await self._handle_reaction_add(data)

            case "MESSAGE_REACTION_REMOVE":
                await self._handle_reaction_remove(data)

            case "MESSAGE_REACTION_REMOVE_ALL":
                await self._handle_reaction_remove_all(data)

            case "MESSAGE_REACTION_REMOVE_EMOJI":
                await self._handle_reaction_remove_emoji(data)

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

    async def _handle_reaction_add(self, data: dict[str, Any]) -> None:
        """Handle MESSAGE_REACTION_ADD event."""
        from .models.reaction import RawReactionActionEvent

        raw = RawReactionActionEvent.from_data(data, "REACTION_ADD")

        # Fire raw event (always fires, even if message not cached)
        await self._fire("on_raw_reaction_add", raw)

        # Search through channels for the message.
        # Message caching is not implemented yet.
        for channel in self._channels.values():
            # Placeholder for future message cache lookup.
            pass

        # For now, we'll just fire the raw event
        # In a complete implementation, you would:
        # 1. Check message cache
        # 2. Update message reactions
        # 3. Fire on_reaction_add with the full Reaction object

    async def _handle_reaction_remove(self, data: dict[str, Any]) -> None:
        """Handle MESSAGE_REACTION_REMOVE event."""
        from .models.reaction import RawReactionActionEvent

        raw = RawReactionActionEvent.from_data(data, "REACTION_REMOVE")

        # Fire raw event (always fires, even if message not cached)
        await self._fire("on_raw_reaction_remove", raw)

    async def _handle_reaction_remove_all(self, data: dict[str, Any]) -> None:
        """Handle MESSAGE_REACTION_REMOVE_ALL event."""
        from .models.reaction import RawReactionClearEvent

        raw = RawReactionClearEvent.from_data(data)

        # Fire raw event (always fires, even if message not cached)
        await self._fire("on_raw_reaction_clear", raw)

    async def _handle_reaction_remove_emoji(self, data: dict[str, Any]) -> None:
        """Handle MESSAGE_REACTION_REMOVE_EMOJI event."""
        from .models.reaction import RawReactionClearEmojiEvent

        raw = RawReactionClearEmojiEvent.from_data(data)

        # Fire raw event (always fires, even if message not cached)
        await self._fire("on_raw_reaction_clear_emoji", raw)

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

    async def fetch_message(self, channel_id: str, message_id: str) -> Message:
        """Fetch a message from the API by channel ID and message ID."""
        assert self._http is not None
        data = await self._http.get_message(channel_id, message_id)
        return Message.from_data(data, self._http)

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

    async def fetch_user_profile(
        self, user_id: str, *, guild_id: str | None = None
    ) -> UserProfile:
        """Fetch a user's full profile from the API.

        This returns additional profile information like bio, pronouns, banner, etc.
        that is not included in the basic user object.

        Args:
            user_id: The user ID to fetch
            guild_id: Optional guild ID for guild-specific profile data

        Returns:
            UserProfile containing the user and their profile information
        """
        assert self._http is not None
        data = await self._http.get_user_profile(user_id, guild_id=guild_id)
        return UserProfile.from_data(data, self._http)

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
    # Reaction methods
    # =========================================================================

    async def add_reaction(
        self, channel_id: int | str, message_id: int | str, emoji: str
    ) -> None:
        """Add a reaction to a message by channel_id and message_id.

        Args:
            channel_id: The channel ID
            message_id: The message ID
            emoji: The emoji to react with (unicode string or custom emoji format)

        Raises:
            Forbidden: You don't have permission to add reactions
            NotFound: The message doesn't exist
            HTTPException: Adding the reaction failed
        """
        assert self._http is not None
        await self._http.add_reaction(channel_id, message_id, emoji)

    async def remove_reaction(
        self,
        channel_id: int | str,
        message_id: int | str,
        emoji: str,
        user_id: int | str = "@me",
    ) -> None:
        """Remove a reaction from a message by channel_id and message_id.

        Args:
            channel_id: The channel ID
            message_id: The message ID
            emoji: The emoji to remove (unicode string or custom emoji format)
            user_id: The user ID to remove the reaction from (default: @me)

        Raises:
            Forbidden: You don't have permission to remove this reaction
            NotFound: The message or reaction doesn't exist
            HTTPException: Removing the reaction failed
        """
        assert self._http is not None
        await self._http.delete_reaction(channel_id, message_id, emoji, user_id)

    async def clear_reactions(
        self, channel_id: int | str, message_id: int | str
    ) -> None:
        """Remove all reactions from a message.

        Args:
            channel_id: The channel ID
            message_id: The message ID

        Raises:
            Forbidden: You don't have permission to clear reactions
            NotFound: The message doesn't exist
            HTTPException: Clearing reactions failed
        """
        assert self._http is not None
        await self._http.delete_all_reactions(channel_id, message_id)

    async def clear_reaction(
        self, channel_id: int | str, message_id: int | str, emoji: str
    ) -> None:
        """Remove all reactions of a specific emoji from a message.

        Args:
            channel_id: The channel ID
            message_id: The message ID
            emoji: The emoji to clear (unicode string or custom emoji format)

        Raises:
            Forbidden: You don't have permission to clear reactions
            NotFound: The message doesn't exist
            HTTPException: Clearing reactions failed
        """
        assert self._http is not None
        await self._http.delete_all_reactions_for_emoji(channel_id, message_id, emoji)

    # =========================================================================
    # Connection lifecycle
    # =========================================================================

    async def start(self, token: str) -> None:
        """Connect to Fluxer and start receiving events (async version).

        Use this if you're managing your own event loop.
        """
        # Create HTTP client with custom API URL if provided
        if self.api_url:
            self._http = HTTPClient(token, api_url=self.api_url)
        else:
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

    Adds prefix command support, cog support, and other bot-specific features.
    This is the recommended class for most bot use cases.

    Args:
        command_prefix: Prefix for text commands (default: "!")
        intents: Gateway intents to request (default: Intents.default())
        api_url: Base URL for the Fluxer API (default: https://api.fluxer.app/v1)
                 Use this to connect to self-hosted Fluxer instances
    """

    def __init__(
        self,
        *,
        command_prefix: str = "!",
        intents: Intents = Intents.default(),
        api_url: str | None = None,
    ) -> None:
        super().__init__(intents=intents, api_url=api_url)
        self.command_prefix = command_prefix
        self._commands: dict[str, EventHandler] = {}
        self._cogs: dict[str, Any] = {}  # Store loaded cogs
        self._extensions: dict[str, Any] = {}  # Store loaded extensions

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
            async def ping(ctx):
                await ctx.reply("Pong!")

            @bot.command(name="hello")
            async def greet(ctx):
                await ctx.reply(f"Hello, {ctx.author}!")
        """

        def decorator(func: EventHandler) -> EventHandler:
            cmd_name = name or func.__name__
            self._commands[cmd_name] = func
            self._commands = dict(
                sorted(self._commands.items(), key=lambda kv: len(kv[0]), reverse=True)
            )  # sorts the dictionary in reverse key length order
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
        # Use list() to avoid RuntimeError if commands dict is modified during iteration
        for cmd, handler in list(self._commands.items()):
            if content.startswith(cmd):
                if handler:
                    try:
                        # Parse arguments based on function signature
                        args_str = content[len(cmd):].strip()
                        await self._invoke_command(handler, message, args_str)
                    except TypeError as e:
                        # Handle missing required arguments
                        if "missing" in str(e) and "required" in str(e):
                            await message.reply(f"❌ Error: {e}")
                        else:
                            raise
                    except Exception:
                        log.exception("Error in command '%s'", cmd)
                    break

    async def _invoke_command(
        self, handler: EventHandler, message: Message, args_str: str
    ) -> None:
        """Parse arguments and invoke a command handler.

        Supports:
        - Positional arguments: async def cmd(ctx, arg1, arg2)
        - Keyword-only arguments: async def cmd(ctx, *, message)
        - Type hints: async def cmd(ctx, count: int)
        - Default values: async def cmd(ctx, message: str = "default")
        """
        sig = inspect.signature(handler)
        params = list(sig.parameters.values())

        # First parameter is always the ctx (context/message)
        if not params or params[0].name != "ctx":
            # If function doesn't take ctx as first param, just pass message
            await handler(message)
            return

        # Remove the ctx parameter from processing
        params = params[1:]

        # Check if there are any parameters that need parsing
        if not params:
            await handler(message)
            return

        # Check for keyword-only parameters (indicated by * in signature)
        # e.g., async def say(ctx, *, message: str)
        has_kwonly = any(
            p.kind == inspect.Parameter.KEYWORD_ONLY for p in params
        )

        if has_kwonly and len(params) == 1:
            # Single keyword-only argument captures all remaining text
            param = params[0]

            # Check if argument was provided
            if not args_str and param.default == inspect.Parameter.empty:
                raise TypeError(
                    f"{handler.__name__}() missing 1 required keyword-only argument: '{param.name}'"
                )

            # Use default if no args provided
            if not args_str:
                await handler(message)
                return

            # Convert to the appropriate type if type hint exists
            value = self._convert_argument(args_str, param.annotation)
            await handler(message, **{param.name: value})
        else:
            # Multiple positional or mixed arguments
            # Split args_str into individual arguments
            args = args_str.split() if args_str else []

            # Build the argument list
            call_args = [message]
            call_kwargs = {}

            for i, param in enumerate(params):
                if param.kind == inspect.Parameter.KEYWORD_ONLY:
                    # Keyword-only args capture remaining text
                    remaining = " ".join(args[i:]) if i < len(args) else ""
                    if not remaining and param.default == inspect.Parameter.empty:
                        raise TypeError(
                            f"{handler.__name__}() missing 1 required keyword-only argument: '{param.name}'"
                        )
                    if remaining:
                        value = self._convert_argument(remaining, param.annotation)
                        call_kwargs[param.name] = value
                    break
                else:
                    # Positional argument
                    if i < len(args):
                        value = self._convert_argument(args[i], param.annotation)
                        call_args.append(value)
                    elif param.default != inspect.Parameter.empty:
                        # Use default value
                        break
                    else:
                        raise TypeError(
                            f"{handler.__name__}() missing 1 required positional argument: '{param.name}'"
                        )

            await handler(*call_args, **call_kwargs)

    def _convert_argument(self, value: str, annotation: Any) -> Any:
        """Convert a string argument to the appropriate type based on annotation."""
        if annotation == inspect.Parameter.empty or annotation == str:
            return value

        try:
            if annotation == int:
                return int(value)
            elif annotation == float:
                return float(value)
            elif annotation == bool:
                return value.lower() in ("true", "1", "yes", "y")
            else:
                # Try to call the annotation as a constructor
                return annotation(value)
        except (ValueError, TypeError):
            # If conversion fails, return as string
            return value

    # =========================================================================
    # Cog management
    # =========================================================================

    async def add_cog(self, cog: Any) -> None:
        """Add a cog to the bot.

        Args:
            cog: An instance of a Cog subclass.

        Example:
            class MyCog(Cog):
                @Cog.command()
                async def hello(self, ctx):
                    await ctx.reply("Hello!")

            bot = Bot()
            await bot.add_cog(MyCog(bot))
        """
        cog_name = cog.__class__.__name__

        if cog_name in self._cogs:
            raise ValueError(f"Cog '{cog_name}' is already loaded")

        # Register cog's commands
        for cmd_name, handler in cog._commands.items():
            if cmd_name in self._commands:
                log.warning(
                    "Command '%s' from cog '%s' overwrites existing command",
                    cmd_name,
                    cog_name,
                )
            self._commands[cmd_name] = handler

        # Register cog's event listeners
        for event_name, listeners in cog._listeners.items():
            for listener in listeners:
                # Add to the client's event handlers
                if event_name not in self._event_handlers:
                    self._event_handlers[event_name] = []
                self._event_handlers[event_name].append(listener)

        # Store the cog
        self._cogs[cog_name] = cog

        # Call the cog's load hook
        await cog.cog_load()

        log.info("Loaded cog: %s", cog_name)

    async def remove_cog(self, cog_name: str) -> None:
        """Remove a cog from the bot.

        Args:
            cog_name: The name of the cog class to remove.

        Example:
            await bot.remove_cog("MyCog")
        """
        if cog_name not in self._cogs:
            raise ValueError(f"Cog '{cog_name}' is not loaded")

        cog = self._cogs[cog_name]

        # Call the cog's unload hook
        await cog.cog_unload()

        # Remove cog's commands
        for cmd_name in list(cog._commands.keys()):
            self._commands.pop(cmd_name, None)

        # Remove cog's event listeners
        for event_name, listeners in cog._listeners.items():
            if event_name in self._event_handlers:
                for listener in listeners:
                    try:
                        self._event_handlers[event_name].remove(listener)
                    except ValueError:
                        pass

        # Remove the cog
        del self._cogs[cog_name]

        log.info("Removed cog: %s", cog_name)

    async def reload_cog(self, cog_name: str) -> None:
        """Reload a cog by removing and re-adding it.

        This is useful during development to reload code changes without restarting the bot.
        Note: You'll need to reimport the module and create a new instance.

        Args:
            cog_name: The name of the cog class to reload.

        Example:
            import importlib
            import my_cogs

            # Reload the module
            importlib.reload(my_cogs)

            # Remove old cog
            await bot.remove_cog("MyCog")

            # Add new cog
            await bot.add_cog(my_cogs.MyCog(bot))
        """
        if cog_name not in self._cogs:
            raise ValueError(f"Cog '{cog_name}' is not loaded")

        # For simple reload, just remove and let the user re-add
        await self.remove_cog(cog_name)
        log.info("Cog '%s' removed. Please re-add it with add_cog().", cog_name)

    def get_cog(self, cog_name: str) -> Any | None:
        """Get a loaded cog by name.

        Args:
            cog_name: The name of the cog class.

        Returns:
            The cog instance, or None if not found.
        """
        return self._cogs.get(cog_name)

    @property
    def cogs(self) -> dict[str, Any]:
        """Get all loaded cogs."""
        return self._cogs.copy()

    # =========================================================================
    # Extension management (discord.py compatible)
    # =========================================================================

    async def load_extension(self, name: str) -> None:
        """Load an extension (module) containing cogs and commands.

        This works like discord.py's load_extension method. The extension must have
        a setup() function that takes the bot instance as an argument.

        Args:
            name: The module path (e.g., "cogs.moderation" or "my_cogs.fun")

        Example:
            # In cogs/moderation.py:
            from fluxer import Cog

            class ModerationCog(Cog):
                @Cog.command()
                async def ban(self, message):
                    await message.reply("Ban command!")

            async def setup(bot):
                await bot.add_cog(ModerationCog(bot))

            # In your main bot file:
            await bot.load_extension("cogs.moderation")
        """
        if name in self._extensions:
            raise ValueError(f"Extension '{name}' is already loaded")

        # Import the module
        try:
            module = importlib.import_module(name)
        except ImportError as e:
            raise ImportError(f"Failed to import extension '{name}': {e}") from e

        # Check if module has a setup function
        if not hasattr(module, "setup"):
            raise AttributeError(
                f"Extension '{name}' is missing a setup() function. "
                "Extensions must have an async setup(bot) function."
            )

        setup = module.setup

        # Call the setup function
        try:
            if inspect.iscoroutinefunction(setup):
                await setup(self)
            else:
                setup(self)
        except Exception as e:
            raise RuntimeError(
                f"Failed to load extension '{name}': {e}"
            ) from e

        # Store the module
        self._extensions[name] = module
        log.info("Loaded extension: %s", name)

    async def unload_extension(self, name: str) -> None:
        """Unload an extension.

        Args:
            name: The module path of the extension to unload.

        Example:
            await bot.unload_extension("cogs.moderation")
        """
        if name not in self._extensions:
            raise ValueError(f"Extension '{name}' is not loaded")

        module = self._extensions[name]

        # Call teardown function if it exists
        if hasattr(module, "teardown"):
            teardown = module.teardown
            try:
                if inspect.iscoroutinefunction(teardown):
                    await teardown(self)
                else:
                    teardown(self)
            except Exception:
                log.exception("Error in teardown for extension '%s'", name)

        # Remove from sys.modules to allow fresh reload
        if name in sys.modules:
            del sys.modules[name]

        # Remove from extensions dict
        del self._extensions[name]
        log.info("Unloaded extension: %s", name)

    async def reload_extension(self, name: str) -> None:
        """Reload an extension by unloading and loading it again.

        This is useful during development to reload code changes without restarting.

        Args:
            name: The module path of the extension to reload.

        Example:
            await bot.reload_extension("cogs.moderation")
        """
        if name not in self._extensions:
            raise ValueError(f"Extension '{name}' is not loaded")

        # Unload and reload
        await self.unload_extension(name)
        await self.load_extension(name)
        log.info("Reloaded extension: %s", name)

    @property
    def extensions(self) -> dict[str, Any]:
        """Get all loaded extensions."""
        return self._extensions.copy()
