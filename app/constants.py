"""共有定数"""

from typing import Final, Literal

# tool_type 文字列値（単一定義 → 各ファイルで import して使用）
TOOL_TYPE_MCP: Final[str] = "mcp"
TOOL_TYPE_CLAUDE_SKILL: Final[str] = "claude_skill"

# tool_type の型エイリアス（_crawl_and_save など内部関数の引数型に使用）
ToolType = Literal["mcp", "claude_skill"]

# tool_type の有効値集合
VALID_TOOL_TYPES: Final[frozenset[str]] = frozenset({TOOL_TYPE_MCP, TOOL_TYPE_CLAUDE_SKILL})
VALID_CRAWL_TARGETS: Final[frozenset[str]] = VALID_TOOL_TYPES | frozenset({"all"})
