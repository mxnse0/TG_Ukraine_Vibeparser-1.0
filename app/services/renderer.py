"""Order card renderer (Pillow) + optional real page screenshots (Playwright)."""

from __future__ import annotations

import asyncio
import io
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.config import Settings
from app.models import Order
from app.parsers import parser_meta
from app.utils.text import clean_for_image, format_money, truncate
from app.utils.time import human_time

log = logging.getLogger(__name__)

WIDTH = 1080
PADDING = 64
BG_TOP = (9, 14, 26)
BG_BOTTOM = (17, 27, 48)
TEXT = (240, 244, 255)
MUTED = (148, 163, 184)
DIVIDER = (38, 50, 74)
CHIP_BG = (30, 42, 64)
GREEN = (74, 222, 128)

_FONT_FILES = {
    False: ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"),
    True: ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"),
}


class Renderer:
    def __init__(self, config: Settings) -> None:
        self.config = config
        self.mode = config.screenshot_mode
        self._font_cache: dict[tuple[bool, int], ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}
        self._shots = PageScreenshots(config) if self.mode == "page" else None

    async def render(self, order: Order) -> bytes:
        if self._shots is not None:
            try:
                return await self._shots.capture(order.url)
            except Exception as exc:  # noqa: BLE001 - fall back to a reliable card
                log.warning("Page screenshot failed for %s: %s. Falling back to card.", order.url, exc)
        return await asyncio.to_thread(self._render_card, order)

    async def close(self) -> None:
        if self._shots is not None:
            await self._shots.close()

    # ------------------------------------------------------------------- card
    def _render_card(self, order: Order) -> bytes:
        meta = parser_meta().get(order.source, {})
        accent = _hex_to_rgb(str(meta.get("color", "#2563eb")))
        source_title = str(meta.get("title", order.source))

        title = clean_for_image(order.title) or "Без назви"
        description = clean_for_image(order.description)
        budget = clean_for_image(order.budget_text)
        if not budget:
            if order.budget_min is not None:
                budget = "≈ " + format_money(order.budget_min, order.currency or "UAH")
            else:
                budget = "не вказано"
        tags = []
        for tag in order.tags:
            cleaned = clean_for_image(tag)
            if cleaned and cleaned.casefold() not in {t.casefold() for t in tags}:
                tags.append(cleaned)
        tags = tags[:6]

        title_font = self._font(True, 46)
        budget_font = self._font(True, 38)
        desc_font = self._font(False, 28)
        label_font = self._font(True, 21)
        meta_font = self._font(False, 24)
        chip_font = self._font(False, 24)
        small_font = self._font(False, 20)
        kicker_font = self._font(True, 22)

        scratch = ImageDraw.Draw(Image.new("RGB", (10, 10)))
        content_width = WIDTH - PADDING * 2

        title_lines = _wrap(scratch, title, title_font, content_width, 4)
        desc_lines = _wrap(scratch, description, desc_font, content_width, 13) if description else []

        chip_rows = _layout_chips(scratch, tags, chip_font, content_width)
        chip_height = len(chip_rows) * 46 if chip_rows else 0

        y = PADDING
        y += 48 + 34  # header
        y += 34  # kicker
        y += len(title_lines) * 58 + 18
        y += 58  # budget
        y += 34  # divider area
        if desc_lines:
            y += 32 + len(desc_lines) * 40 + 18
        if chip_height:
            y += chip_height + 22
        footer_height = 206
        height = max(880, y + footer_height + PADDING)

        image = _gradient(WIDTH, height)
        draw = ImageDraw.Draw(image)

        # Accent line on top
        draw.rectangle([0, 0, WIDTH, 6], fill=accent)

        # Header: source badge + time
        badge_text = source_title.upper()
        badge_w = int(draw.textlength(badge_text, font=kicker_font)) + 34
        draw.rounded_rectangle(
            [PADDING, PADDING, PADDING + badge_w, PADDING + 48],
            radius=24,
            fill=_blend(BG_TOP, accent, 0.22),
            outline=_blend(BG_TOP, accent, 0.55),
            width=1,
        )
        draw.text(
            (PADDING + 17, PADDING + 12),
            badge_text,
            font=kicker_font,
            fill=_lighten(accent, 0.35),
        )

        time_text = human_time(order.published_at, self.config.tz)
        time_w = draw.textlength(time_text, font=meta_font)
        draw.text((WIDTH - PADDING - time_w, PADDING + 12), time_text, font=meta_font, fill=MUTED)

        y = PADDING + 48 + 34
        draw.text((PADDING, y), "НОВЕ ЗАМОВЛЕННЯ", font=kicker_font, fill=accent)
        y += 34

        for line in title_lines:
            draw.text((PADDING, y), line, font=title_font, fill=TEXT)
            y += 58
        y += 18

        draw.text((PADDING, y), budget, font=budget_font, fill=GREEN if budget != "не вказано" else MUTED)
        y += 58

        draw.line([(PADDING, y), (WIDTH - PADDING, y)], fill=DIVIDER, width=2)
        y += 34

        if desc_lines:
            draw.text((PADDING, y), "ОПИС", font=label_font, fill=MUTED)
            y += 32
            for line in desc_lines:
                draw.text((PADDING, y), line, font=desc_font, fill=(214, 223, 240))
                y += 40
            y += 18

        if chip_rows:
            y = _draw_chips(draw, chip_rows, chip_font, PADDING, y)
            y += 22

        # Footer
        footer_y = height - PADDING - 168
        draw.line([(PADDING, footer_y - 24), (WIDTH - PADDING, footer_y - 24)], fill=DIVIDER, width=2)

        draw.text((PADDING, footer_y), "VibeParser", font=self._font(True, 26), fill=TEXT)
        draw.text(
            (PADDING, footer_y + 38),
            f"{source_title} · {human_time(order.published_at, self.config.tz)}",
            font=small_font,
            fill=MUTED,
        )
        url_text = truncate(order.url, 62)
        draw.text((PADDING, footer_y + 74), url_text, font=small_font, fill=(96, 165, 250))

        qr_size = 150
        qr_img = _make_qr(order.url, qr_size)
        qr_x = WIDTH - PADDING - qr_size
        qr_y = footer_y - 4
        draw.rounded_rectangle(
            [qr_x - 8, qr_y - 8, qr_x + qr_size + 8, qr_y + qr_size + 8],
            radius=10,
            fill=(255, 255, 255),
        )
        image.paste(qr_img, (qr_x, qr_y))
        qr_label = "сканувати"
        qr_label_w = draw.textlength(qr_label, font=small_font)
        draw.text(
            (qr_x + (qr_size - qr_label_w) / 2, qr_y + qr_size + 12),
            qr_label,
            font=small_font,
            fill=MUTED,
        )

        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=88, optimize=True)
        return buffer.getvalue()

    def _font(self, bold: bool, size: int):
        key = (bold, size)
        if key in self._font_cache:
            return self._font_cache[key]
        path = _find_font(bold)
        font = None
        if path is not None:
            try:
                font = ImageFont.truetype(str(path), size=size)
            except OSError:
                font = None
        if font is None:
            try:
                font = ImageFont.load_default(size=size)
            except TypeError:  # very old Pillow
                font = ImageFont.load_default()
        self._font_cache[key] = font
        return font


class PageScreenshots:
    """Optional Playwright-based screenshot of the real order page."""

    def __init__(self, config: Settings) -> None:
        self.config = config
        self._playwright = None
        self._browser = None
        self._lock = asyncio.Lock()

    async def _ensure_browser(self):
        if self._browser is not None:
            return self._browser
        from playwright.async_api import async_playwright  # lazy optional dependency

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        return self._browser

    async def capture(self, url: str) -> bytes:
        async with self._lock:
            browser = await self._ensure_browser()
            context = await browser.new_context(
                viewport={"width": 1280, "height": 1600},
                user_agent=self.config.user_agent,
                locale="uk-UA",
            )
            try:
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2500)
                title = (await page.title()).lower()
                if "just a moment" in title or "cloudflare" in title:
                    raise RuntimeError("Cloudflare challenge")
                data = await page.screenshot(full_page=False, type="jpeg", quality=85)
                return data
            finally:
                await context.close()

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None


# --------------------------------------------------------------------- helpers
def _find_font(bold: bool) -> Path | None:
    roots = [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
        Path("/usr/share/fonts/truetype/dejavu"),
        Path("/usr/share/fonts/truetype/liberation"),
        Path("/Library/Fonts"),
        Path("/System/Library/Fonts"),
    ]
    for name in _FONT_FILES[bold]:
        for root in roots:
            candidate = root / name
            if candidate.exists():
                return candidate
    return None


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int, max_lines: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    words = re.split(r"\s+", text)
    lines: list[str] = []
    current = ""
    for word in words:
        if draw.textlength(word, font=font) > max_width:
            # Hard-break an overlong word/URL.
            if current:
                lines.append(current)
                current = ""
            while word and len(lines) < max_lines:
                part = word
                while part and draw.textlength(part, font=font) > max_width:
                    part = part[:-1]
                if not part:
                    break
                lines.append(part)
                word = word[len(part):]
            current = word
            continue
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
            if len(lines) >= max_lines:
                break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
    if lines and len(" ".join(lines)) < len(text):
        last = lines[-1]
        while last and draw.textlength(last + "…", font=font) > max_width:
            last = last[:-1]
        lines[-1] = last.rstrip() + "…"
    return lines


def _layout_chips(draw: ImageDraw.ImageDraw, tags: list[str], font, max_width: int) -> list[list[str]]:
    rows: list[list[str]] = []
    row: list[str] = []
    row_width = 0
    for tag in tags:
        chip_w = int(draw.textlength(tag, font=font)) + 34
        if row and row_width + chip_w + 12 > max_width:
            rows.append(row)
            row, row_width = [], 0
            if len(rows) == 2:
                break
        row.append(tag)
        row_width += chip_w + 12
    if row and len(rows) < 2:
        rows.append(row)
    return rows


def _draw_chips(draw: ImageDraw.ImageDraw, rows: list[list[str]], font, x0: int, y0: int) -> int:
    y = y0
    for row in rows:
        x = x0
        for tag in row:
            chip_w = int(draw.textlength(tag, font=font)) + 34
            draw.rounded_rectangle(
                [x, y, x + chip_w, y + 40], radius=20, fill=CHIP_BG, outline=DIVIDER
            )
            draw.text((x + 17, y + 7), tag, font=font, fill=(203, 213, 225))
            x += chip_w + 12
        y += 46
    return y


def _gradient(width: int, height: int) -> Image.Image:
    image = Image.new("RGB", (width, height), BG_TOP)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        ratio = y / max(1, height - 1)
        color = tuple(
            int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * ratio) for i in range(3)
        )
        draw.line([(0, y), (width, y)], fill=color)
    return image


def _make_qr(url: str, size: int) -> Image.Image:
    import qrcode

    qr = qrcode.QRCode(box_size=6, border=1, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image(fill_color="#0b1220", back_color="white").convert("RGB")
    return image.resize((size, size), Image.Resampling.NEAREST)


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    if len(value) != 6:
        return (37, 99, 235)
    try:
        return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return (37, 99, 235)


def _blend(base: tuple[int, int, int], accent: tuple[int, int, int], ratio: float) -> tuple[int, int, int]:
    return tuple(int(base[i] + (accent[i] - base[i]) * ratio) for i in range(3))  # type: ignore[return-value]


def _lighten(color: tuple[int, int, int], ratio: float) -> tuple[int, int, int]:
    return tuple(int(c + (255 - c) * ratio) for c in color)  # type: ignore[return-value]


def demo_order() -> Order:
    return Order(
        source="freelancehunt",
        external_id="demo",
        title="Розробка Telegram-бота для моніторингу замовлень з оплатою",
        url="https://freelancehunt.com/",
        description=(
            "Потрібен досвідчений Python-розробник для створення бота, який збирає "
            "нові замовлення з кількох фриланс-бірж, фільтрує їх за ключовими словами "
            "та надсилає у Telegram із зручними кнопками. Бажано мати досвід з aiogram, "
            "httpx, SQLite та парсингом HTML. Оплата за етапами, довгострокова співпраця."
        ),
        budget_text="12 000 UAH",
        budget_min=12000,
        budget_max=12000,
        currency="UAH",
        category="Розробка ботів",
        tags=["Python", "Telegram Bot", "Парсинг", "aiogram"],
        published_at=datetime.now(timezone.utc),
    )
