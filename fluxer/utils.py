from __future__ import annotations

import os
import pkgutil
import re
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Literal

# Fluxer uses the same epoch as Discord: 2015-01-01T00:00:00Z
FLUXER_EPOCH = 1420070400000


def snowflake_to_datetime(snowflake: str | int) -> datetime:
    """Convert a Fluxer Snowflake ID to a datetime.

    Snowflakes encode a timestamp in the upper 42 bits.

    Args:
        snowflake: The Snowflake ID as a string or int.

    Returns:
        A timezone-aware UTC datetime.
    """
    timestamp_ms = (int(snowflake) >> 22) + FLUXER_EPOCH
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)


def datetime_to_snowflake(dt: datetime) -> int:
    """Convert a datetime to a Snowflake ID (useful for pagination).

    This creates a Snowflake with only the timestamp component set.
    Useful for before/after pagination parameters.

    Args:
        dt: A datetime object.

    Returns:
        A Snowflake integer.
    """
    timestamp_ms = int(dt.timestamp() * 1000)
    snowflake = (timestamp_ms - FLUXER_EPOCH) << 22
    return snowflake


def utcnow() -> datetime:
    """A helper function to return an aware UTC datetime representing the current time.

    This should be preferred to :meth:`datetime.datetime.utcnow` since it is an aware
    datetime, compared to the naive datetime in the standard library.

    Returns
    -------
    :class:`datetime.datetime`
        The current aware datetime in UTC.
    """
    return datetime.now(timezone.utc)


_MARKDOWN_ESCAPE_SUBREGEX = "|".join(
    rf"\{c}(?=([\s\S]*((?<!\{c})\{c})))" for c in ("*", "`", "_", "~", "|")
)

_MARKDOWN_ESCAPE_COMMON = r"^>(?:>>)?\s|\[.+\]\(.+\)"

_MARKDOWN_ESCAPE_REGEX = re.compile(
    rf"(?P<markdown>{_MARKDOWN_ESCAPE_SUBREGEX}|{_MARKDOWN_ESCAPE_COMMON})",
    re.MULTILINE,
)

_URL_REGEX = r"(?P<url><[^: >]+:\/[^ >]+>|(?:https?|steam):\/\/[^\s<]+[^<.,:;\"\'\]\s])"

_MARKDOWN_STOCK_REGEX = rf"(?P<markdown>[_\\~|\*`]|{_MARKDOWN_ESCAPE_COMMON})"


def remove_markdown(text: str, *, ignore_links: bool = True) -> str:
    """A helper function that removes markdown characters.

    .. note::
            This function is not markdown aware and may remove meaning from the original text. For example,
            if the input contains ``10 * 5`` then it will be converted into ``10  5``.

    Parameters
    ----------
    text: :class:`str`
        The text to remove markdown from.
    ignore_links: :class:`bool`
        Whether to leave links alone when removing markdown. For example,
        if a URL in the text contains characters such as ``_`` then it will
        be left alone. Defaults to ``True``.

    Returns
    -------
    :class:`str`
        The text with the markdown special characters removed.
    """

    def replacement(match: re.Match) -> str:
        groupdict = match.groupdict()
        return groupdict.get("url", "")

    regex = _MARKDOWN_STOCK_REGEX
    if ignore_links:
        regex = f"(?:{_URL_REGEX}|{regex})"
    return re.sub(regex, replacement, text, flags=re.MULTILINE)


def escape_markdown(
    text: str, *, as_needed: bool = False, ignore_links: bool = True
) -> str:
    r"""A helper function that escapes Fluxer's markdown.

    Parameters
    ----------
    text: :class:`str`
        The text to escape markdown from.
    as_needed: :class:`bool`
        Whether to escape the markdown characters as needed. This
        means that it does not escape extraneous characters if it's
        not necessary, e.g. ``**hello**`` is escaped into ``\*\*hello**``
        instead of ``\*\*hello\*\*``. Note however that this can open
        you up to some clever syntax abuse. Defaults to ``False``.
    ignore_links: :class:`bool`
        Whether to leave links alone when escaping markdown. For example,
        if a URL in the text contains characters such as ``_`` then it will
        be left alone. This option is not supported with ``as_needed``.
        Defaults to ``True``.

    Returns
    -------
    :class:`str`
        The text with the markdown special characters escaped with a slash.
    """
    if not as_needed:

        def replacement(match: re.Match) -> str:
            groupdict = match.groupdict()
            is_url = groupdict.get("url")
            if is_url:
                return is_url
            return "\\" + groupdict["markdown"]

        regex = _MARKDOWN_STOCK_REGEX
        if ignore_links:
            regex = f"(?:{_URL_REGEX}|{regex})"
        return re.sub(regex, replacement, text, flags=re.MULTILINE)
    else:
        text = re.sub(r"\\", r"\\\\", text)
        return _MARKDOWN_ESCAPE_REGEX.sub(r"\\\1", text)


TimestampStyle = Literal["t", "T", "d", "D", "f", "F", "s", "S", "R"]


def format_dt(dt: datetime | float, /, style: TimestampStyle = "f") -> str:
    """Format a :class:`datetime.datetime`, :class:`int` or :class:`float` (seconds) for presentation within Fluxer.

    This allows for a locale-independent way of presenting data using Fluxer specific Markdown.

    +-------------+-------------------------------+------------------------+
    |    Style    |        Example Output         |      Description       |
    +=============+===============================+========================+
    | t           | 22:57                         | Short Time             |
    +-------------+-------------------------------+------------------------+
    | T           | 22:57:58                      | Long Time              |
    +-------------+-------------------------------+------------------------+
    | d           | 17/05/2016                    | Short Date             |
    +-------------+-------------------------------+------------------------+
    | D           | 17 May 2016                   | Long Date              |
    +-------------+-------------------------------+------------------------+
    | f (default) | 17 May 2016 at 22:57          | Long Date, Short Time  |
    +-------------+-------------------------------+------------------------+
    | F           | Tuesday, 17 May 2016 at 22:57 | Full Date, Short Time  |
    +-------------+-------------------------------+------------------------+
    | s           | 17/05/2016, 22:57             | Short Date, Short Time |
    +-------------+-------------------------------+------------------------+
    | S           | 17/05/2016, 22:57:58          | Short Date, Long Time  |
    +-------------+-------------------------------+------------------------+
    | R           | 5 years ago                   | Relative Time          |
    +-------------+-------------------------------+------------------------+

    Note that the exact output depends on the user's locale setting in the client. The example output
    presented is using the ``en-GB`` locale.

    Parameters
    ----------
    dt: :class:`datetime.datetime` | :class:`int` | :class:`float`
        The datetime to format.
        If this is a naive datetime, it is assumed to be local time.
    style: :class:`str`
        The style to format the datetime with. Defaults to ``f``

    Returns
    -------
    :class:`str`
        The formatted string.
    """
    if isinstance(dt, datetime):
        dt = dt.timestamp()
    return f"<t:{int(dt)}:{style}>"


def search_directory(path: str) -> Iterator[str]:
    """Walk through a directory and yield all modules.

    Parameters
    ----------
    path: :class:`str`
        The path to search for modules

    Yields
    ------
    :class:`str`
        The name of the found module. (usable in load_extension)
    """
    relpath = os.path.relpath(path)  # relative and normalized
    if ".." in relpath:
        msg = "Modules outside the cwd require a package to be specified"
        raise ValueError(msg)

    abspath = os.path.abspath(path)
    if not os.path.exists(relpath):
        msg = f"Provided path '{abspath}' does not exist"
        raise ValueError(msg)
    if not os.path.isdir(relpath):
        msg = f"Provided path '{abspath}' is not a directory"
        raise ValueError(msg)

    prefix = relpath.replace(os.sep, ".")
    if prefix in ("", "."):
        prefix = ""
    else:
        prefix += "."

    for _, name, ispkg in pkgutil.iter_modules([path]):
        if ispkg:
            yield from search_directory(os.path.join(path, name))
        else:
            yield prefix + name
