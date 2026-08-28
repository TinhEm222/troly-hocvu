from dataclasses import dataclass
from typing import Any

# schema duoc dung de dinh nghia cau truc cua tai lieu duoc truy xuat tu he thong truy van.
@dataclass
class RetrievedDocument:
    id: str
    score: float
    text: str
    metadata: dict[str, Any]
