import re


def md_to_html(text: str) -> str:
    """Convert basic markdown to Telegram HTML."""
    # Bold: **text** → <b>text</b>
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text, flags=re.DOTALL)
    # Italic: _text_ → <i>text</i>
    text = re.sub(r'(?<!\w)_(.+?)_(?!\w)', r'<i>\1</i>', text)
    # Code: `text` → <code>text</code>
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    return text


def chunk_message(text: str, max_length: int = 4000) -> list[str]:
    """Split long messages into chunks respecting max_length."""
    if len(text) <= max_length:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:max_length])
        text = text[max_length:]
    return chunks
