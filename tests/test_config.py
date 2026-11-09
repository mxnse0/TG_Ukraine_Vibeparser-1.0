"""Configuration, paths and single-instance behaviour."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.config import Settings
from app.paths import BASE_DIR, RESOURCE_DIR, app_dir, is_frozen, resource_dir
from app.utils.single_instance import SingleInstance


def test_paths_resolve_to_project_root_in_source_mode() -> None:
    assert is_frozen() is False
    assert app_dir() == BASE_DIR
    assert resource_dir() == RESOURCE_DIR
    assert (BASE_DIR / "main.py").exists()


def test_relative_data_paths_are_resolved_against_base_dir() -> None:
    settings = Settings(
        _env_file=None,
        data_dir=Path("relative/data"),
        db_path=Path("relative/data/test.db"),
    )
    assert settings.data_dir.is_absolute()
    assert settings.db_path.is_absolute()
    assert settings.data_dir == (BASE_DIR / "relative/data").resolve()
    assert settings.db_path == (BASE_DIR / "relative/data/test.db").resolve()


def test_env_template_is_available_for_frozen_builds() -> None:
    template = RESOURCE_DIR / ".env.example"
    assert template.exists()
    text = template.read_text(encoding="utf-8")
    assert "BOT_TOKEN=" in text


def test_bot_token_validation_rejects_example_value() -> None:
    assert Settings(_env_file=None, bot_token="").has_valid_bot_token is False
    assert Settings(_env_file=None, bot_token="123456789:AA...").has_valid_bot_token is False
    real_looking = "123456789:" + "A" * 35
    assert Settings(_env_file=None, bot_token=real_looking).has_valid_bot_token is True


def test_single_instance_blocks_second_process(tmp_path) -> None:
    name = f"VibeParserTest-{uuid4().hex}"
    lock_path = tmp_path / "vibeparser.lock"

    first = SingleInstance(lock_path, name=name)
    second = SingleInstance(lock_path, name=name)
    third = SingleInstance(lock_path, name=name)

    assert first.acquire() is True
    try:
        assert second.acquire() is False
    finally:
        first.release()

    assert third.acquire() is True
    third.release()
