from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Embed:
    """Builder for rich embed objects.

    Usage:
        embed = Embed(title="Hello", description="World", color=0x5865F2)
        embed.add_field(name="Field 1", value="Value 1")
        embed.set_footer(text="Footer text")
        await channel.send(embed=embed)
    """

    title: str | None = None
    description: str | None = None
    url: str | None = None
    color: int | None = None
    timestamp: str | None = None
    footer: dict[str, Any] | None = None
    image: dict[str, Any] | None = None
    thumbnail: dict[str, Any] | None = None
    author: dict[str, Any] | None = None
    fields: list[dict[str, Any]] = field(default_factory=list)

    def set_footer(self, *, text: str, icon_url: str | None = None) -> Embed:
        self.footer = {"text": text}
        if icon_url:
            self.footer["icon_url"] = icon_url
        return self

    def set_image(self, *, url: str) -> Embed:
        self.image = {"url": url}
        return self

    def set_thumbnail(self, *, url: str) -> Embed:
        self.thumbnail = {"url": url}
        return self

    def set_author(
        self, *, name: str, url: str | None = None, icon_url: str | None = None
    ) -> Embed:
        self.author = {"name": name}
        if url:
            self.author["url"] = url
        if icon_url:
            self.author["icon_url"] = icon_url
        return self

    def add_field(self, *, name: str, value: str, inline: bool = False) -> Embed:
        self.fields.append({"name": name, "value": value, "inline": inline})
        return self

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict suitable for the API."""
        d: dict[str, Any] = {}
        if self.title is not None:
            d["title"] = self.title
        if self.description is not None:
            d["description"] = self.description
        if self.url is not None:
            d["url"] = self.url
        if self.color is not None:
            d["color"] = self.color
        if self.timestamp is not None:
            d["timestamp"] = self.timestamp
        if self.footer is not None:
            d["footer"] = self.footer
        if self.image is not None:
            d["image"] = self.image
        if self.thumbnail is not None:
            d["thumbnail"] = self.thumbnail
        if self.author is not None:
            d["author"] = self.author
        if self.fields:
            d["fields"] = self.fields
        return d
