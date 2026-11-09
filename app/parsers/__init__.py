"""Parser registry."""

from __future__ import annotations

from app.parsers.base import BaseParser
from app.parsers.djinni import DjinniParser
from app.parsers.flru import FlRuParser
from app.parsers.freelance_ua import FreelanceUaParser
from app.parsers.freelancehunt import FreelanceHuntParser
from app.parsers.freelancer_com import FreelancerComParser
from app.parsers.kwork import KworkParser
from app.parsers.weblancer import WeblancerParser

PARSER_CLASSES: list[type[BaseParser]] = [
    FreelanceHuntParser,
    WeblancerParser,
    FreelanceUaParser,
    FreelancerComParser,
    DjinniParser,
    KworkParser,
    FlRuParser,
]

DEFAULT_SOURCES = [cls.name for cls in PARSER_CLASSES if cls.default_enabled]


def build_parsers(rates: dict[str, float] | None = None) -> dict[str, BaseParser]:
    return {cls.name: cls(rates=rates) for cls in PARSER_CLASSES}


def parser_meta() -> dict[str, dict[str, object]]:
    """Static metadata used by the bot (title, colour, default state)."""
    return {
        cls.name: {
            "title": cls.title,
            "color": cls.color,
            "default_enabled": cls.default_enabled,
        }
        for cls in PARSER_CLASSES
    }
