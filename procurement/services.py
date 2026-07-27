import json
from decimal import Decimal
from urllib.request import urlopen, Request
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

def get_exchange_rate(currency_code: str, target: str = 'USD') -> dict:
    """Fetch exchange rate from `currency_code` to `target` using exchangerate.host.
    Checks the local database cache first.

    Returns dict: {'rate': Decimal, 'source': 'exchangerate.host', 'timestamp': '...'}
    On failure returns {'rate': Decimal(1), 'source': 'local-fallback'}
    """
    from .models import ExchangeRate, Currency # Late import to avoid circular dependency
    
    if not currency_code:
        return {'rate': Decimal(1), 'source': 'invalid'}
    
    currency_code = currency_code.upper()
    target = (target or 'USD').upper()
    
    if currency_code == target:
        return {'rate': Decimal(1), 'source': 'same-currency'}

    # 0. Check if both currencies exist in the Currency model and use their exchange_rate_to_usd
    try:
        base_c = Currency.objects.get(code=currency_code)
        target_c = Currency.objects.get(code=target)
        rate_val = target_c.exchange_rate_to_usd / base_c.exchange_rate_to_usd
        return {
            'rate': rate_val,
            'source': 'local-currency-table',
            'timestamp': timezone.now().isoformat()
        }
    except Currency.DoesNotExist:
        pass

    # 1. Check Database for recent exchange rate (e.g., within 24 hours)
    # Ignore bad cache files (fetch-failed / no-rate)
    twenty_four_hours_ago = timezone.now() - timedelta(hours=24)
    cached_rate = ExchangeRate.objects.filter(
        currency=currency_code, 
        target_currency=target, 
        retrieved_at__gte=twenty_four_hours_ago
    ).exclude(source__in=['fetch-failed', 'no-rate']).order_by('-retrieved_at').first()

    if cached_rate:
        return {
            'rate': cached_rate.rate,
            'source': cached_rate.source or 'db-cache',
            'timestamp': cached_rate.retrieved_at.isoformat()
        }

    # 2. Fetch from API if no recent cache exists
    EXCHANGERATE_HOST = 'https://api.exchangerate.host/latest'
    url = f"{EXCHANGERATE_HOST}?base={currency_code}&symbols={target}"
    req = Request(url, headers={'User-Agent': 'afraa-fuel-system/1.0'})
    
    rate_val = None
    source = 'fetch-failed'
    timestamp = timezone.now().isoformat()
    
    try:
        with urlopen(req, timeout=5) as resp:
            data = json.load(resp)
            rates = data.get('rates', {})
            val = rates.get(target)
            if val is not None:
                rate_val = Decimal(str(val))
                source = 'exchangerate.host'
                timestamp = data.get('date', timestamp)
            else:
                source = 'no-rate'
    except Exception as e:
        logger.warning(f"Failed to fetch exchange rate {currency_code}->{target}: {e}")
        source = 'fetch-failed'

    # Fallback if API failed or no rate returned
    if rate_val is None:
        try:
            base_c = Currency.objects.get(code=currency_code)
            target_c = Currency.objects.get(code=target)
            rate_val = target_c.exchange_rate_to_usd / base_c.exchange_rate_to_usd
            source = 'local-currency-table'
        except Exception:
            # Check old cached rates as final fallback
            old_rate = ExchangeRate.objects.filter(
                currency=currency_code, 
                target_currency=target
            ).exclude(source__in=['fetch-failed', 'no-rate']).order_by('-retrieved_at').first()
            if old_rate:
                return {
                    'rate': old_rate.rate,
                    'source': f"{old_rate.source} (stale fallback)",
                    'timestamp': old_rate.retrieved_at.isoformat()
                }
            rate_val = Decimal(1)
            source = 'local-fallback-default'

    # 3. Save to database
    try:
        ExchangeRate.objects.create(
            currency=currency_code,
            target_currency=target,
            rate=rate_val,
            source=source
        )
    except Exception as e:
        logger.warning(f"Failed to save exchange rate to DB: {e}")

    return {'rate': rate_val, 'source': source, 'timestamp': timestamp}