"""Filter loading and matching."""

from __future__ import annotations

from app.db import Database
from app.models import Filters
from app.utils.text import split_terms


async def load_filters(db: Database) -> Filters:
    return Filters(
        keywords=split_terms(await db.get_setting("keywords", "")),
        exclude_keywords=split_terms(await db.get_setting("exclude_keywords", "")),
        min_budget=await db.get_float("min_budget", 0.0),
        max_budget=await db.get_float("max_budget", 0.0),
        skip_no_budget=await db.get_bool("skip_no_budget", False),
    )
