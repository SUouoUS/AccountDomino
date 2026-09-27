"""경로 애니메이션 HTML 렌더링(외부 리소스 없는 자체 완결 페이지)."""
from __future__ import annotations

import json
from pathlib import Path

TEMPLATE_PATH = Path(__file__).resolve().parent / "static" / "domino_animation.html"


def render(payload: dict) -> str:
    """build_animation_payload() 결과를 템플릿에 주입한다."""
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE_PATH.read_text(encoding="utf-8").replace("__DATA__", data)
