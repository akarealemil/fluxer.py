from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

        """Delete this emoji from its guild.

        Args:
            reason: Reason for deletion (shows in audit log)

        Raises:
            Forbidden: You don't have permission to delete emojis
            NotFound: Emoji doesn't exist
            HTTPException: Deleting the emoji failed
        """
        if not self._http:
            raise RuntimeError("Cannot delete emoji without HTTPClient")
        if not self.guild_id:
            raise RuntimeError("Cannot delete emoji without guild_id")

        await self._http.delete_guild_emoji(self.guild_id, self.id, reason=reason)

    def __str__(self) -> str:
        return f"<{'a' if self.animated else ''}:{self.name}:{self.id}>"
