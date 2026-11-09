"""Parser unit tests using local HTML/API fixtures (no network)."""

from __future__ import annotations

from bs4 import BeautifulSoup

from app.parsers.djinni import DjinniParser
from app.parsers.flru import FlRuParser
from app.parsers.freelance_ua import FreelanceUaParser
from app.parsers.freelancehunt import FreelanceHuntParser
from app.parsers.freelancer_com import FreelancerComParser
from app.parsers.weblancer import WeblancerParser

RATES = {"UAH": 1.0, "USD": 41.0, "EUR": 45.0, "RUB": 0.45}


def test_freelancehunt_api_item() -> None:
    parser = FreelanceHuntParser(rates=RATES)
    order = parser._parse_item(
        {
            "id": 1663481,
            "attributes": {
                "name": "Утеплення дверей",
                "description": "<p>Треба зробити</p>",
                "budget": {"amount": 2000, "currency": "UAH"},
                "skills": [{"name": "Будівництво"}],
                "published_at": "2026-11-08T10:00:00+00:00",
                "bid_count": 3,
            },
            "links": {"self": {"web": "https://freelancehunt.com/project/x/1663481.html"}},
        }
    )
    assert order is not None
    assert order.external_id == "1663481"
    assert order.budget_min == 2000
    assert order.category == "Будівництво"
    assert order.published_at is not None


def test_freelancer_api_project() -> None:
    parser = FreelancerComParser(rates=RATES)
    order = parser._parse_project(
        {
            "id": 40808797,
            "title": "Scraping project",
            "seo_url": "data-entry/Romanian-Company-Database-Scrapping",
            "currency": {"code": "USD"},
            "budget": {"minimum": 15, "maximum": 30},
            "description": "<p>Scrape data</p>",
            "jobs": [{"name": "Data Entry", "category": {"name": "Data Entry"}}],
            "time_submitted": 1762596000,
            "bid_stats": {"bid_count": 4},
        }
    )
    assert order is not None
    assert order.budget_text == "15 USD – 30 USD"
    assert order.budget_max == 30 * RATES["USD"]
    assert order.url.startswith("https://www.freelancer.com/projects/")


def test_weblancer_article() -> None:
    html = """
    <article>
      <div class="flex justify-between items-start">
        <h2><a href="/ua/freelance/veb-programmirovanie-31/test-1270439/">Створення бота</a></h2>
        <span class="text-green-600 text-xl whitespace-nowrap">1000 $</span>
      </div>
      <p class="text-gray-600">Потрібен Telegram-бот</p>
      <div class="flex flex-wrap gap-2"><a href="/ua/freelance/bots/">Боти</a></div>
      <div><span>08.11.2026</span></div>
    </article>
    """
    parser = WeblancerParser(rates=RATES)
    card = BeautifulSoup(html, "lxml").find("article")
    order = parser._parse_article(card)
    assert order is not None
    assert order.external_id == "1270439"
    assert order.budget_min == 41000
    assert order.category == "Боти"
    assert order.published_at is not None


def test_freelance_ua_card() -> None:
    html = """
    <li class="j-order">
      <header class="l-project-title">
        <a href="https://freelance.ua/orders/298222-test.html">Створення бота</a>
      </header>
      <div class="l-project-head"><span class="l-price">50000 грн.</span></div>
      <article><p>Потрібен бот</p></article>
      <ul class="l-item-features"><li>сьогодні</li></ul>
    </li>
    """
    parser = FreelanceUaParser(rates=RATES)
    card = BeautifulSoup(html, "lxml").select_one("li.j-order")
    order = parser._parse_card(card)
    assert order is not None
    assert order.external_id == "298222"
    assert order.budget_min == 50000
    assert order.budget_text == "50000 грн."


def test_rss_parsers_use_beautifulsoup_api(monkeypatch) -> None:
    """Djinni/FL.ru used ElementTree's findtext on BS4 tags, which broke RSS."""
    rss = """<?xml version="1.0"?>
    <rss><channel>
      <item>
        <title>Python developer</title>
        <link>https://djinni.co/jobs/123456-python-developer/</link>
        <description>Фікс від $1000 до $3500</description>
        <category>Python</category>
        <pubDate>Sat, 08 Nov 2026 10:00:00 +0000</pubDate>
      </item>
    </channel></rss>"""

    class FakeResponse:
        text = rss

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        async def get(self, *args, **kwargs):
            return FakeResponse()

    import asyncio

    orders = asyncio.run(DjinniParser(rates=RATES).fetch(FakeClient()))
    assert len(orders) == 1
    assert orders[0].external_id == "123456"
    assert orders[0].budget_min == 41000

    flru_orders = asyncio.run(FlRuParser(rates=RATES).fetch(FakeClient()))
    assert len(flru_orders) == 1
    assert flru_orders[0].title == "Python developer"
