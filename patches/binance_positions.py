"""
Binance Position Filter Patch for NautilusTrader

This module patches the Binance HTTP client to filter out non-ASCII symbols
from position reports BEFORE they are parsed by the Rust code.

Why this is needed:
    - Binance returns positions like '币安人生USDT' (Chinese characters)
    - NautilusTrader's Rust code panics on non-ASCII symbols
    - The panic happens during parsing, before any Python filtering can occur
    - This patch intercepts the JSON response to filter data before parsing

Usage:
    from patches.binance_positions import apply_position_filter_patch
    apply_position_filter_patch()

Important:
    - Requires aiohttp to be installed
    - Install with: pip install aiohttp
"""

import logging
from functools import wraps

logger = logging.getLogger(__name__)

# Check if aiohttp is available
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    logger.warning(
        "aiohttp is not installed. Position filter patch cannot be applied. "
        "Install with: pip install aiohttp"
    )

_position_patch_applied = False
_warned_symbols = set()


def is_ascii_symbol(symbol: str) -> bool:
    """Check if symbol contains only ASCII characters."""
    if not symbol:
        return True
    try:
        symbol.encode('ascii')
        return True
    except UnicodeEncodeError:
        return False


def filter_non_ascii_positions(data):
    """
    Filter non-ASCII symbols from position data.

    Parameters
    ----------
    data : list or dict
        Position data from Binance API

    Returns
    -------
    list or dict
        Filtered data
    """
    global _warned_symbols

    if isinstance(data, list):
        filtered = []
        for item in data:
            if isinstance(item, dict):
                symbol = item.get('symbol', '')
                if symbol and not is_ascii_symbol(symbol):
                    if symbol not in _warned_symbols:
                        _warned_symbols.add(symbol)
                        logger.warning(f"Filtering non-ASCII symbol from positions: {symbol}")
                    continue
            filtered.append(item)
        return filtered
    elif isinstance(data, dict):
        # Filter 'positions' array if present
        if 'positions' in data and isinstance(data['positions'], list):
            original_count = len(data['positions'])
            data['positions'] = filter_non_ascii_positions(data['positions'])
            filtered_count = original_count - len(data['positions'])
            if filtered_count > 0:
                logger.info(f"Filtered {filtered_count} non-ASCII positions from account data")
        return data
    return data


def apply_position_filter_patch() -> bool:
    """
    Apply patch to filter non-ASCII symbols from Binance responses.

    This patches the JSON decoder used by aiohttp to filter position data.

    Returns
    -------
    bool
        True if patch was applied successfully.
    """
    global _position_patch_applied

    if _position_patch_applied:
        logger.debug("Position filter patch already applied")
        return True

    # Check if aiohttp is available
    if not AIOHTTP_AVAILABLE:
        logger.error(
            "❌ Cannot apply position filter patch: aiohttp is not installed.\n"
            "   This is required to filter non-ASCII symbols like '币安人生USDT'.\n"
            "   Install with: pip install aiohttp"
        )
        return False

    try:
        # Store original json method
        original_json = aiohttp.ClientResponse.json

        @wraps(original_json)
        async def filtered_json(self, *args, **kwargs):
            """Wrapper that filters non-ASCII symbols from Binance responses."""
            result = await original_json(self, *args, **kwargs)

            # Check if this is a Binance futures API response
            url = str(self.url)
            if 'fapi.binance.com' in url or 'dapi.binance.com' in url:
                # Filter position-related endpoints
                if '/positionRisk' in url or '/account' in url:
                    result = filter_non_ascii_positions(result)

            return result

        # Apply the patch
        aiohttp.ClientResponse.json = filtered_json

        _position_patch_applied = True
        logger.info("✅ Patched aiohttp.ClientResponse.json for non-ASCII symbol filtering")
        return True

    except Exception as e:
        logger.error(f"Failed to apply position filter patch: {e}")
        return False


def apply_http_response_filter() -> bool:
    """
    Alias for apply_position_filter_patch for backward compatibility.
    """
    return apply_position_filter_patch()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    print("Testing position filter patch...")

    # Test ASCII check
    assert is_ascii_symbol("BTCUSDT") == True
    assert is_ascii_symbol("ETHUSDT") == True
    assert is_ascii_symbol("币安人生USDT") == False
    assert is_ascii_symbol("") == True
    assert is_ascii_symbol(None) == True  # Will return True due to early check
    print("✅ ASCII check works")

    # Test filter function - list
    test_list = [
        {"symbol": "BTCUSDT", "positionAmt": "1.0"},
        {"symbol": "币安人生USDT", "positionAmt": "0"},
        {"symbol": "ETHUSDT", "positionAmt": "2.0"},
    ]
    filtered_list = filter_non_ascii_positions(test_list)
    assert len(filtered_list) == 2
    assert filtered_list[0]["symbol"] == "BTCUSDT"
    assert filtered_list[1]["symbol"] == "ETHUSDT"
    print("✅ List filter works")

    # Test filter function - dict with positions
    test_dict = {
        "totalMarginBalance": "1000",
        "positions": [
            {"symbol": "BTCUSDT", "positionAmt": "1.0"},
            {"symbol": "币安人生USDT", "positionAmt": "0"},
        ]
    }
    filtered_dict = filter_non_ascii_positions(test_dict)
    assert len(filtered_dict["positions"]) == 1
    assert filtered_dict["positions"][0]["symbol"] == "BTCUSDT"
    print("✅ Dict filter works")

    print("✅ All tests passed!")
