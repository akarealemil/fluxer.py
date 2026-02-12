from __future__ import annotations

import enum

# =============================================================================
# Gateway Opcodes
# Fluxer mirrors Discord's opcode structure since it's wire-compatible.
# =============================================================================


class GatewayOpcode(enum.IntEnum):
    """Gateway opcodes define the type of payload being sent/received."""

    DISPATCH = 0  # Server -> Client: An event was dispatched
    HEARTBEAT = 1  # Bidirectional: Maintain connection / request heartbeat
    IDENTIFY = 2  # Client -> Server: Start a new session
    PRESENCE_UPDATE = 3  # Client -> Server: Update client presence/status
    VOICE_STATE_UPDATE = 4  # Client -> Server: Join/move/leave voice channels
    RESUME = 6  # Client -> Server: Resume a dropped connection
    RECONNECT = 7  # Server -> Client: Client should reconnect
    REQUEST_GUILD_MEMBERS = 8  # Client -> Server: Request guild member list
    INVALID_SESSION = 9  # Server -> Client: Session is invalid
    HELLO = 10  # Server -> Client: Sent on connect, contains heartbeat_interval
    HEARTBEAT_ACK = 11  # Server -> Client: Acknowledgement of heartbeat


# =============================================================================
# Gateway Intents
# Bit flags that tell the gateway which events you want to receive.
# =============================================================================


class Intents(enum.IntFlag):
    """Gateway intents control which events your bot receives.

    Usage:
        intents = Intents.GUILDS | Intents.GUILD_MESSAGES
        intents = Intents.default()
        intents = Intents.all()
    """

    GUILDS = 1 << 0
    GUILD_MEMBERS = 1 << 1
    GUILD_MODERATION = 1 << 2
    GUILD_EMOJIS_AND_STICKERS = 1 << 3
    GUILD_INTEGRATIONS = 1 << 4
    GUILD_WEBHOOKS = 1 << 5
    GUILD_INVITES = 1 << 6
    GUILD_VOICE_STATES = 1 << 7
    GUILD_PRESENCES = 1 << 8
    GUILD_MESSAGES = 1 << 9
    GUILD_MESSAGE_REACTIONS = 1 << 10
    GUILD_MESSAGE_TYPING = 1 << 11
    DIRECT_MESSAGES = 1 << 12
    DIRECT_MESSAGE_REACTIONS = 1 << 13
    DIRECT_MESSAGE_TYPING = 1 << 14
    MESSAGE_CONTENT = 1 << 15

    @classmethod
    def default(cls) -> Intents:
        """Returns a sensible default set of intents (excludes privileged ones)."""
        value = cls(0)
        for intent in cls:
            if intent not in (
                cls.GUILD_MEMBERS,
                cls.GUILD_PRESENCES,
                cls.MESSAGE_CONTENT,
            ):
                value |= intent
        return value

    @classmethod
    def all(cls) -> Intents:
        """Returns all intents enabled."""
        value = cls(0)
        for intent in cls:
            value |= intent
        return value

    @classmethod
    def none(cls) -> Intents:
        """Returns no intents."""
        return cls(0)


# =============================================================================
# Gateway Close Codes
# =============================================================================


class GatewayCloseCode(enum.IntEnum):
    """WebSocket close codes the Fluxer gateway may send."""

    UNKNOWN_ERROR = 4000
    UNKNOWN_OPCODE = 4001
    DECODE_ERROR = 4002
    NOT_AUTHENTICATED = 4003
    AUTHENTICATION_FAILED = 4004
    ALREADY_AUTHENTICATED = 4005
    INVALID_SEQ = 4007
    RATE_LIMITED = 4008
    SESSION_TIMED_OUT = 4009
    INVALID_SHARD = 4010
    SHARDING_REQUIRED = 4011
    INVALID_API_VERSION = 4012
    INVALID_INTENTS = 4013
    DISALLOWED_INTENTS = 4014

    @property
    def is_reconnectable(self) -> bool:
        """Whether the bot should attempt to reconnect after this close code."""
        non_reconnectable = {
            self.AUTHENTICATION_FAILED,
            self.INVALID_SHARD,
            self.SHARDING_REQUIRED,
            self.INVALID_API_VERSION,
            self.INVALID_INTENTS,
            self.DISALLOWED_INTENTS,
        }
        return self not in non_reconnectable


# =============================================================================
# Channel Types
# =============================================================================


class ChannelType(enum.IntEnum):
    GUILD_TEXT = 0
    DM = 1
    GUILD_VOICE = 2
    GROUP_DM = 3
    GUILD_CATEGORY = 4
    GUILD_ANNOUNCEMENT = 5
