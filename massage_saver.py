import json
from datetime import datetime
from pathlib import Path

_log_path: Path = Path("logs/chat_logs.jsonl")

def save_message(chat_id: int, role: str, content: str) -> None:

    _log_path.parent.mkdir(parents=True, exist_ok=True)

    log_entry = {
        "chat_id": chat_id,
        "role": role,
        "content": content,
        "timestamp": datetime.utcnow().isoformat()
    }

    with _log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
