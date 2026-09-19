# Blueprints self-register at import time:
#   from app import registry
#   registry.register("my_tab", "My Tab", "myblueprint.myview")

from __future__ import annotations

_registry: dict[str, dict] = {}


def register(key: str, name: str, endpoint: str, icon: str = "") -> None:
    _registry[key] = {"name": name, "endpoint": endpoint, "icon": icon}


def get_registry() -> dict[str, dict]:
    return dict(_registry)


def known_tabs() -> dict[str, str]:
    return {k: v["name"] for k, v in _registry.items()}
