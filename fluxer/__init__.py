__version__ = "0.1.0"
__title__ = "fluxer.py"
__author__ = "Emil"
__license__ = "MIT"

# Core classes
from .client import Bot, Client
from .enums import ChannelType, GatewayCloseCode, GatewayOpcode, Intents

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
from .models import Channel, Embed, Emoji, Guild, Message, User

# Utilities
from .utils import datetime_to_snowflake, snowflake_to_datetime

__all__ = [
    # Client
    "Bot",
    "Client",
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
    "Message",
    "User",
    # Utils
    "datetime_to_snowflake",
    "snowflake_to_datetime",
]
