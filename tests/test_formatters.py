import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from bot.formatters import md_to_html, chunk_message


def test_bold_conversion():
    assert md_to_html("**hello**") == "<b>hello</b>"


def test_italic_conversion():
    assert md_to_html("_hello_") == "<i>hello</i>"


def test_code_conversion():
    assert md_to_html("`code`") == "<code>code</code>"


def test_no_change_plain():
    assert md_to_html("plain text") == "plain text"


def test_chunk_short_message():
    result = chunk_message("hello", 4000)
    assert result == ["hello"]


def test_chunk_long_message():
    long_text = "x" * 8500
    chunks = chunk_message(long_text, 4000)
    assert len(chunks) == 3
    assert all(len(c) <= 4000 for c in chunks)


def test_chunk_preserves_content():
    long_text = "a" * 8500
    chunks = chunk_message(long_text, 4000)
    assert "".join(chunks) == long_text
