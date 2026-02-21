from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from fluxer import utils


@pytest.mark.parametrize(
    ("num", "expected"),
    [
        (0, datetime(2015, 1, 1, tzinfo=timezone.utc)),
        (881536165478499999, datetime(2021, 8, 29, 13, 50, 0, tzinfo=timezone.utc)),
        (10000000000000000000, datetime(2090, 7, 20, 17, 49, 51, tzinfo=timezone.utc)),
    ],
)
def test_snowflake_to_datetime(num: int, expected) -> None:
    assert utils.snowflake_to_datetime(num).replace(microsecond=0) == expected


@pytest.mark.parametrize(
    ("dt", "expected"),
    [
        (datetime(2015, 1, 1, tzinfo=timezone.utc), 0),
        (datetime(2021, 8, 29, 13, 50, 0, tzinfo=timezone.utc), 881536165478400000),
    ],
)
def test_datetime_to_snowflake(dt, expected) -> None:
    assert utils.datetime_to_snowflake(dt) == expected


def test_utcnow() -> None:
    assert utils.utcnow().tzinfo == timezone.utc


@pytest.mark.parametrize(
    ("text", "exp_remove", "exp_escape"),
    [
        (
            # this is obviously not valid markdown for the most part,
            # it's just meant to test several combinations
            "*hi* ~~a~ |aaa~*\\``\n`py x``` __uwu__ y",
            "hi a aaa\npy x uwu y",
            r"\*hi\* \~\~a\~ \|aaa\~\*\\\`\`" + "\n" + r"\`py x\`\`\` \_\_uwu\_\_ y",
        ),
        (
            "aaaaa\n> h\n>> abc \n>>> nay*ern_",
            "aaaaa\nh\n>> abc \nnayern",
            "aaaaa\n\\> h\n>> abc \n\\>>> nay\\*ern\\_",
        ),
        (
            "*h*\n> [li|nk](~~url~~) xyz **https://google.com/stuff?uwu=owo",
            "h\n xyz https://google.com/stuff?uwu=owo",
            # NOTE: currently doesn't escape inside `[x](y)`, should that be changed?
            r"\*h\*"
            + "\n"
            + r"\> \[li|nk](~~url~~) xyz \*\*https://google.com/stuff?uwu=owo",
        ),
    ],
)
def test_markdown(text: str, exp_remove, exp_escape) -> None:
    assert utils.remove_markdown(text, ignore_links=False) == exp_remove
    assert utils.remove_markdown(text, ignore_links=True) == exp_remove

    assert utils.escape_markdown(text, ignore_links=False) == exp_escape
    assert utils.escape_markdown(text, ignore_links=True) == exp_escape


@pytest.mark.parametrize(
    ("text", "expected", "expected_ignore"),
    [
        (
            "http://google.com/~test/hi_test ~~a~~",
            "http://google.com/test/hitest a",
            "http://google.com/~test/hi_test a",
        ),
        (
            "abc [link](http://test~test.com)\n>>> <http://endless.horse/_*>",
            "abc \n<http://endless.horse/>",
            "abc \n<http://endless.horse/_*>",
        ),
    ],
)
def test_markdown_links(text: str, expected, expected_ignore) -> None:
    assert utils.remove_markdown(text, ignore_links=False) == expected
    assert utils.remove_markdown(text, ignore_links=True) == expected_ignore


@pytest.mark.parametrize(
    ("dt", "style", "expected"),
    [
        (0, "F", "<t:0:F>"),
        (1630245000.1234, "T", "<t:1630245000:T>"),
        (
            datetime(2021, 8, 29, 13, 50, 0, tzinfo=timezone.utc),
            "f",
            "<t:1630245000:f>",
        ),
    ],
)
def test_format_dt(dt, style, expected) -> None:
    assert utils.format_dt(dt, style) == expected


@pytest.fixture(scope="session")
def tmp_module_root(tmp_path_factory):
    # this obviously isn't great code, but it'll do just fine for tests
    tmpdir = tmp_path_factory.mktemp("module_root")
    for d in ["empty", "not_a_module", "mod/sub1/sub2"]:
        (tmpdir / d).mkdir(parents=True)
    for f in [
        "test.py",
        "not_a_module/abc.py",
        "mod/__init__.py",
        "mod/ext.py",
        "mod/sub1/sub2/__init__.py",
        "mod/sub1/sub2/abc.py",
    ]:
        (tmpdir / f).touch()
    return tmpdir


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (".", ["test", "mod.ext"]),
        ("./", ["test", "mod.ext"]),
        ("empty/", []),
    ],
)
def test_search_directory(tmp_module_root, path, expected) -> None:
    orig_cwd = os.getcwd()
    try:
        os.chdir(tmp_module_root)

        # test relative and absolute paths
        for p in [path, os.path.abspath(path)]:
            assert sorted(utils.search_directory(p)) == sorted(expected)
    finally:
        os.chdir(orig_cwd)


@pytest.mark.parametrize(
    ("path", "exc"),
    [
        ("../../", r"Modules outside the cwd require a package to be specified"),
        ("nonexistent", r"Provided path '.*?nonexistent' does not exist"),
        ("test.py", r"Provided path '.*?test.py' is not a directory"),
    ],
)
def test_search_directory_exc(tmp_module_root, path, exc) -> None:
    orig_cwd = os.getcwd()
    try:
        os.chdir(tmp_module_root)

        with pytest.raises(ValueError, match=exc):
            list(utils.search_directory(tmp_module_root / path))
    finally:
        os.chdir(orig_cwd)
