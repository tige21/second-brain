from langchain_core.tools import tool


@tool
def think(thought: str) -> str:
    """
    Internal reasoning tool. Use this to think through complex decisions before acting.
    Use when: processing long voice recordings (🎙️), before creating multiple items,
    before deciding between Create vs Update, analyzing forwarded messages.
    The thought is not shown to the user.
    Returns: "OK"
    """
    return "OK"
