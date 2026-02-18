"""Cog system for organizing bot commands and event listeners.

Similar to discord.py's cog system, this allows you to group related commands
and event handlers into separate classes for better code organization.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Coroutine

if TYPE_CHECKING:
    from .client import Bot

EventHandler = Callable[..., Coroutine[Any, Any, None]]


class Cog:
    """Base class for creating cogs.

    A cog is a collection of commands and event listeners grouped together.
    This is useful for organizing large bots into logical modules.

    Example:
        class MyCog(Cog):
            def __init__(self, bot):
                super().__init__(bot)

            @Cog.command()
            async def hello(self, message):
                await message.reply("Hello from MyCog!")

            @Cog.listener()
            async def on_message(self, message):
                # This will be called for every message
                pass
    """

    def __init__(self, bot: Bot) -> None:
        """Initialize the cog.

        Args:
            bot: The bot instance this cog is attached to.
        """
        self.bot = bot
        self._commands: dict[str, EventHandler] = {}
        self._listeners: dict[str, list[EventHandler]] = {}

        # Auto-discover commands and listeners from methods
        self._discover_handlers()

    def _discover_handlers(self) -> None:
        """Discover and register all command and listener methods."""
        for name in dir(self):
            # Skip private/magic methods
            if name.startswith("_"):
                continue

            method = getattr(self, name)

            # Check if it's marked as a command
            if hasattr(method, "__cog_command__"):
                cmd_name = getattr(method, "__cog_command_name__", name)
                self._commands[cmd_name] = method

            # Check if it's marked as a listener
            if hasattr(method, "__cog_listener__"):
                event_name = getattr(method, "__cog_listener_name__", name)
                if event_name not in self._listeners:
                    self._listeners[event_name] = []
                self._listeners[event_name].append(method)

    @staticmethod
    def command(name: str | None = None) -> Callable[[EventHandler], EventHandler]:
        """Decorator to mark a method as a command.

        Args:
            name: Optional name for the command. If not provided, uses the method name.

        Example:
            @Cog.command()
            async def ping(self, message):
                await message.reply("Pong!")

            @Cog.command(name="hi")
            async def hello(self, message):
                await message.reply("Hello!")
        """

        def decorator(func: EventHandler) -> EventHandler:
            func.__cog_command__ = True  # type: ignore
            if name is not None:
                func.__cog_command_name__ = name  # type: ignore
            return func

        return decorator

    @staticmethod
    def listener(name: str | None = None) -> Callable[[EventHandler], EventHandler]:
        """Decorator to mark a method as an event listener.

        Args:
            name: Optional event name. If not provided, uses the method name.

        Example:
            @Cog.listener()
            async def on_message(self, message):
                print(f"Message received: {message.content}")

            @Cog.listener(name="on_ready")
            async def bot_ready(self):
                print("Bot is ready!")
        """

        def decorator(func: EventHandler) -> EventHandler:
            func.__cog_listener__ = True  # type: ignore
            if name is not None:
                func.__cog_listener_name__ = name  # type: ignore
            return func

        return decorator

    async def cog_load(self) -> None:
        """Called when the cog is loaded.

        Override this to run setup code when the cog is added to the bot.
        """
        pass

    async def cog_unload(self) -> None:
        """Called when the cog is unloaded.

        Override this to run cleanup code when the cog is removed from the bot.
        """
        pass

    def __repr__(self) -> str:
        return f"<Cog {self.__class__.__name__}>"
