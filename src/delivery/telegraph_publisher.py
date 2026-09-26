import json
import re
import requests
from pathlib import Path
from typing import List, Dict, Any, Union, Optional

from config.settings import BASE_DIR

TOKEN_FILE = BASE_DIR / "data" / ".telegraph_token"

def get_or_create_telegraph_token() -> str:
    """Retrieve cached Telegraph access token or create a new free account."""
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)

    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if token:
            return token

    url = "https://api.telegra.ph/createAccount"
    payload = {
        "short_name": "GarminAI",
        "author_name": "Garmin Health AI"
    }

    try:
        res = requests.post(url, data=payload, timeout=15)
        data = res.json()
        if data.get("ok"):
            token = data["result"]["access_token"]
            TOKEN_FILE.write_text(token, encoding="utf-8")
            return token
    except Exception as exc:
        print(f"⚠️ Failed to create Telegraph account: {exc}")

    return ""

def _inline_markdown_to_nodes(text: str) -> List[Union[str, Dict[str, Any]]]:
    """Parse inline bold (**text**) and italic (*text*) into Telegraph DOM children."""
    if not text:
        return []

    # Pattern for **bold** or *italic* or `code`
    pattern = re.compile(r'(\*\*.*?\*\*|\*.*?\*|`.*?`)')
    parts = pattern.split(text)

    children = []
    for part in parts:
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            children.append({"tag": "b", "children": [part[2:-2]]})
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            children.append({"tag": "i", "children": [part[1:-1]]})
        elif part.startswith("`") and part.endswith("`") and len(part) > 2:
            children.append({"tag": "code", "children": [part[1:-1]]})
        else:
            children.append(part)

    return children

def markdown_to_telegraph_nodes(markdown_text: str) -> List[Dict[str, Any]]:
    """Convert a Markdown document string into Telegraph Node JSON array format."""
    if not markdown_text:
        return []

    nodes: List[Dict[str, Any]] = []
    lines = markdown_text.splitlines()

    in_list = False
    list_items: List[Dict[str, Any]] = []

    def flush_list():
        nonlocal in_list, list_items
        if in_list and list_items:
            nodes.append({"tag": "ul", "children": list_items})
            list_items = []
            in_list = False

    for line in lines:
        stripped = line.strip()

        if not stripped:
            flush_list()
            continue

        if stripped.startswith("---") or stripped.startswith("***"):
            flush_list()
            nodes.append({"tag": "hr"})
            continue

        # Headers
        if stripped.startswith("# "):
            flush_list()
            children = _inline_markdown_to_nodes(stripped[2:])
            nodes.append({"tag": "h3", "children": children})
            continue
        elif stripped.startswith("## ") or stripped.startswith("### "):
            flush_list()
            header_text = re.sub(r"^#{2,3}\s*", "", stripped)
            children = _inline_markdown_to_nodes(header_text)
            nodes.append({"tag": "h4", "children": children})
            continue

        # Bullet List Items
        if stripped.startswith("- ") or stripped.startswith("+ ") or stripped.startswith("* "):
            item_text = stripped[2:]
            item_children = _inline_markdown_to_nodes(item_text)
            list_items.append({"tag": "li", "children": item_children})
            in_list = True
            continue

        # Regular Paragraph
        flush_list()
        children = _inline_markdown_to_nodes(stripped)
        nodes.append({"tag": "p", "children": children})

    flush_list()
    return nodes

def publish_report_to_telegraph(
    title: str,
    markdown_text: str,
    author_name: str = "Garmin Health AI"
) -> str:
    """Publish a full Markdown report to Telegraph and return the public URL (https://telegra.ph/...)."""
    token = get_or_create_telegraph_token()
    if not token:
        raise RuntimeError("Telegraph access token could not be established.")

    nodes = markdown_to_telegraph_nodes(markdown_text)
    if not nodes:
        nodes = [{"tag": "p", "children": ["Không có nội dung báo cáo."]}]

    # Clean title for Telegraph
    clean_title = re.sub(r"[#*_`~]", "", title).strip() or "Báo cáo Sinh lý học Garmin Health AI"

    url = "https://api.telegra.ph/createPage"
    payload = {
        "access_token": token,
        "title": clean_title[:256],
        "author_name": author_name,
        "content": json.dumps(nodes, ensure_ascii=False),
        "return_content": False
    }

    res = requests.post(url, data=payload, timeout=(15, 60))
    data = res.json()

    if data.get("ok"):
        page_url = data["result"]["url"]
        return page_url
    else:
        err_msg = data.get("error") or str(data)
        raise RuntimeError(f"Telegraph API createPage failed: {err_msg}")
