from __future__ import annotations

from datetime import date as date_type
from datetime import timedelta
import httpx
from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Optional, Tuple, Dict

from loguru import logger

# Decimal precision high enough for currency math, rounded to 2 at the edge
getcontext().prec = 28

# Simple in-memory cache: {(code, yyyy-mm-dd): Decimal(rate_to_eur)}
_CACHE: Dict[Tuple[str, str], Decimal] = {}

FRANKFURTER_URL = "https://api.frankfurter.app/{day}?from={code}&to=EUR"
EXHOST_URL = "https://api.exchangerate.host/convert?from={code}&to=EUR&amount=1&date={day}"
FAWAZ_URL = "https://cdn.jsdelivr.net/gh/fawazahmed0/currency-api@{vers}/currencies/{code}/eur.json"
FLOATRATES_URL = "https://www.floatrates.com/daily/{code}.json"


def _normalize_code(code: str) -> str:
    c = (code or "").strip().upper()
    if c == "USDT":  # treat USDT as USD-peg
        return "USD"
    return c


async def _exhost_rate(code_n: str, day_str: str) -> Optional[Decimal]:
    url = EXHOST_URL.format(code=code_n, day=day_str)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
            # Prefer explicit rate if present
            rate = (data.get("info", {}) or {}).get("rate")
            if rate is None:
                # Some responses return only result for amount=1
                rate = data.get("result")
            if rate is None:
                logger.warning(f"exchangerate.host: no EUR rate for {code_n} on {day_str}")
                return None
            return Decimal(str(rate))
    except httpx.HTTPError as e:
        logger.error(f"exchangerate.host HTTP error for {code_n} {day_str}: {e}")
        return None
    except Exception as e:
        logger.exception(e)
        return None


async def _fawaz_rate(code_n: str, day_str: str) -> Optional[Decimal]:
    # day_str: "latest" or "YYYY-MM-DD"
    vers = "latest" if day_str == "latest" else day_str
    url = FAWAZ_URL.format(vers=vers, code=code_n.lower())
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
            val = data.get("eur")
            if val is None:
                logger.warning(f"fawaz: no EUR for {code_n} on {day_str}")
                return None
            return Decimal(str(val))
    except httpx.HTTPError as e:
        logger.debug(f"fawaz HTTP error {code_n} {day_str}: {e}")
        return None
    except Exception as e:
        logger.debug(f"fawaz unexpected {code_n} {day_str}: {e}")
        return None


async def _floatrates_rate(code_n: str, day_str: str) -> Optional[Decimal]:
    """
    Floatrates: returns JSON for base=code_n; take lowercase key 'eur'.
    Ignores day_str (latest-only), but we keep signature uniform.
    """
    url = FLOATRATES_URL.format(code=code_n.lower())
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
            eur = (data.get("eur") or {}).get("rate")
            if eur is None:
                logger.warning(f"floatrates: no EUR for {code_n}")
                return None
            return Decimal(str(eur))
    except httpx.HTTPError as e:
        logger.debug(f"floatrates HTTP error {code_n}: {e}")
        return None
    except Exception as e:
        logger.debug(f"floatrates unexpected {code_n}: {e}")
        return None


async def get_rate_to_eur(code: str, day: date_type) -> Optional[Decimal]:
    """Return 1 unit of `code` in EUR for the given day.
    Strategy: Frankfurter (latest/dated) → fallback to exchangerate.host; try up to 5 days back.
    Cache successful result under the original requested date (day.isoformat()) to stabilize output.
    """
    code_n = _normalize_code(code)
    if not code_n:
        return None
    if code_n == "EUR":
        return Decimal("1")

    # Build list of day strings to try
    tries: list[str] = []
    today_iso = date_type.today().isoformat()
    if day == date_type.today():
        tries.append("latest")
    tries.append(day.isoformat())
    for i in range(1, 6):  # up to 5 days back
        tries.append((day - timedelta(days=i)).isoformat())

    requested_key = (code_n, day.isoformat())

    # Return from cache if already known for the exact requested day
    if requested_key in _CACHE:
        return _CACHE[requested_key]

    for day_str in tries:
        cache_key = (code_n, day_str)
        if cache_key in _CACHE:
            # also pin to requested day cache for stability
            _CACHE[requested_key] = _CACHE[cache_key]
            return _CACHE[cache_key]

        # 1) Try Frankfurter
        try:
            url = FRANKFURTER_URL.format(day=day_str, code=code_n)
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(url)
                r.raise_for_status()
                data = r.json()
                rate = data.get("rates", {}).get("EUR")
                if rate is not None:
                    rate_dec = Decimal(str(rate))
                    _CACHE[cache_key] = rate_dec
                    _CACHE[requested_key] = rate_dec
                    return rate_dec
        except httpx.HTTPError as e:
            logger.debug(f"Frankfurter HTTP error for {code_n} {day_str}: {e}")
        except Exception as e:
            logger.debug(f"Frankfurter unexpected error for {code_n} {day_str}: {e}")

        # 2) Fallback: exchangerate.host (no 'latest' support → use today when needed)
        ex_day = day_str if day_str != "latest" else today_iso
        rate_dec = await _exhost_rate(code_n, ex_day)
        if rate_dec is not None:
            _CACHE[cache_key] = rate_dec
            _CACHE[requested_key] = rate_dec
            return rate_dec

        # 3) Final fallback: Fawaz currency API via jsDelivr
        rate_dec = await _fawaz_rate(code_n, day_str)
        if rate_dec is not None:
            _CACHE[cache_key] = rate_dec
            _CACHE[requested_key] = rate_dec
            return rate_dec

        # 4) Floatrates final fallback (latest only)
        rate_dec = await _floatrates_rate(code_n, day_str)
        if rate_dec is not None:
            _CACHE[cache_key] = rate_dec
            _CACHE[requested_key] = rate_dec
            return rate_dec

    return None


async def convert_to_eur(amount: Decimal, code: str, day: date_type) -> Optional[Decimal]:
    """Convert `amount` of `code` to EUR using daily rate. Returns Decimal rounded to 2 places, or None."""
    try:
        rate = await get_rate_to_eur(code, day)
        if rate is None:
            return None
        eur = (amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return eur
    except Exception as e:
        logger.exception(e)
        return None