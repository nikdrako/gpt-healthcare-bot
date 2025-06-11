import json
from pathlib import Path

_log_path: Path = Path("logs/users_history.jsonl")

def save_message_history(chat_id: int, role: str, content: str) -> None:
    _log_path.parent.mkdir(parents=True, exist_ok=True)
    if role == 'user':
        log_entry = {
         "chat_id": chat_id,
         "role": role,
         "content": content,
      }
        with _log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")