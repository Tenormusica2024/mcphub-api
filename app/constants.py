"""共有定数"""

from typing import Final

# tool_type の有効値（単一定義 → admin.py / servers.py / crawler.py が参照）
VALID_TOOL_TYPES: Final[frozenset[str]] = frozenset({"mcp", "claude_skill"})
VALID_CRAWL_TARGETS: Final[frozenset[str]] = VALID_TOOL_TYPES | frozenset({"all"})
