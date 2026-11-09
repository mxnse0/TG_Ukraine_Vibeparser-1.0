"""Submit a bid to Freelancehunt via the official API (optional feature)."""

from __future__ import annotations

import logging

import httpx

log = logging.getLogger(__name__)


class BidError(RuntimeError):
    pass


async def place_bid(
    *,
    token: str,
    project_id: str,
    comment: str,
    amount: float,
    currency: str,
    days: int,
    is_hidden: bool = True,
    timeout: float = 30.0,
) -> str:
    if not token:
        raise BidError("FREELANCEHUNT_TOKEN не налаштований")
    if not comment.strip():
        raise BidError("Порожній текст відгуку")
    if amount <= 0:
        raise BidError("Сума має бути більшою за 0")
    if days <= 0:
        raise BidError("Термін має бути більшим за 0")

    payload = {
        "days": int(days),
        "safe_type": "employer",
        "budget": {"amount": round(float(amount), 2), "currency": currency or "UAH"},
        "comment": comment.strip(),
        "is_hidden": bool(is_hidden),
    }
    url = f"https://api.freelancehunt.com/v2/projects/{project_id}/bids"

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, json=payload, headers={"Authorization": token})
        if response.status_code in (401, 403):
            # Some API clients use "Bearer <token>"; support both formats.
            response = await client.post(
                url, json=payload, headers={"Authorization": f"Bearer {token}"}
            )
        if response.status_code >= 400:
            detail = _extract_error(response)
            raise BidError(f"Freelancehunt {response.status_code}: {detail}")
    return "Відгук успішно надіслано на Freelancehunt"


def _extract_error(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return response.text[:300]
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            return str(error.get("title") or error.get("detail") or error)[:300]
        if error:
            return str(error)[:300]
        errors = data.get("errors")
        if errors:
            return str(errors)[:300]
    return str(data)[:300]
