import json
from pathlib import Path
from typing import List, Dict

_log_path: Path = Path("logs/users_history.jsonl")

def load_chat_history(chat_id: int, limit: int = 100) -> List[Dict[str, str]]:
    messages = []
    if not _log_path.exists():
        return messages

    with _log_path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                if entry.get("chat_id") == chat_id:
                    messages.append({
                        "role": entry.get("role"),
                        "content": entry.get("content")
                    })
            except json.JSONDecodeError:
                continue

    return messages[-limit:]
