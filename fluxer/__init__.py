__version__ = "0.3.1"
__title__ = "fluxer.py"
__author__ = "Emil"
__license__ = "MIT"

# Core classes
from .client import Bot, Client
from .cog import Cog
from .enums import ChannelType, GatewayCloseCode, GatewayOpcode, Intents
from .file import File
from .http import HTTPClient

# Errors
from .errors import (
    BadRequest,
    FluxerException,
    Forbidden,
    GatewayException,
    GatewayNotConnected,
    HTTPException,
    LoginFailure,
    NotFound,
    RateLimited,
    Unauthorized,
)

# Models
from .models import Channel, Embed, Emoji, Guild, GuildMember, Message, User, UserProfile, Webhook

# Utilities
from .utils import datetime_to_snowflake, snowflake_to_datetime

__all__ = [
    # Client
    "Bot",
    "Client",
    "Cog",
    "File",
    "HTTPClient",
    # Enums
    "ChannelType",
    "GatewayCloseCode",
    "GatewayOpcode",
    "Intents",
    # Errors
    "BadRequest",
    "FluxerException",
    "Forbidden",
    "GatewayException",
    "GatewayNotConnected",
    "HTTPException",
    "LoginFailure",
    "NotFound",
    "RateLimited",
    "Unauthorized",
    # Models
    "Channel",
    "Embed",
    "Emoji",
    "Guild",
    "GuildMember",
    "Message",
    "User",
    "UserProfile",
    "Webhook",
    # Utils
    "datetime_to_snowflake",
    "snowflake_to_datetime",
]
