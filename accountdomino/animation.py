"""경로 시뮬레이션 컴포넌트(st.components.v2, 외부 리소스 없음). 데이터는 JSON(data=)으로만 넘긴다."""
from __future__ import annotations

from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parent / "static"
ASSETS = {"html": "simulation.html", "css": "simulation.css", "js": "simulation.js"}


def assets() -> dict[str, str]:
    """컴포넌트를 구성하는 HTML·CSS·JS 원문."""
    return {kind: (STATIC_DIR / name).read_text(encoding="utf-8") for kind, name in ASSETS.items()}


def register():
    """Streamlit 에 시뮬레이션 컴포넌트를 등록하고 마운트 함수를 돌려준다.

    마운트: ``mount(key=..., data=build_animation_payload(...), on_exit_change=callback)``
    X 또는 Esc → 종료 확인 → '종료'를 누르면 exit 트리거가 Python 으로 전달된다.
    """
    import streamlit as st

    return st.components.v2.component("domino_simulation", **assets())
