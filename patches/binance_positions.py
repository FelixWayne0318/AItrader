"""
Binance Position Filter Patch for NautilusTrader

This module patches aiohttp to filter out non-ASCII symbols from Binance API
responses BEFORE they are parsed by NautilusTrader's Rust/msgspec code.

Why this is needed:
    - Binance returns positions like '币安人生USDT' (Chinese characters)
    - NautilusTrader's Rust code panics on non-ASCII symbols
    - NautilusTrader uses msgspec to decode directly from bytes (not resp.json())
    - We must intercept at the read() level, not json() level

Usage:
    from patches.binance_positions import apply_position_filter_patch
    apply_position_filter_patch()

Important:
    - Requires aiohttp to be installed
    - Must be applied BEFORE any NautilusTrader imports
"""

import json
import logging
import re
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


def filter_non_ascii_from_json_bytes(data: bytes, url: str) -> bytes:
    """
    Filter non-ASCII symbols from JSON bytes data.

    This function parses JSON bytes, filters out entries with non-ASCII symbols,
    and returns the filtered JSON as bytes.

    Parameters
    ----------
    data : bytes
        Raw JSON bytes from Binance API
    url : str
        The request URL (for logging)

    Returns
    -------
    bytes
        Filtered JSON bytes
    """
    global _warned_symbols

    try:
        # Decode bytes to string, then parse JSON
        text = data.decode('utf-8')
        parsed = json.loads(text)

        modified = False

        # Handle list response (e.g., /positionRisk)
        if isinstance(parsed, list):
            original_len = len(parsed)
            filtered = []
            for item in parsed:
                if isinstance(item, dict):
                    symbol = item.get('symbol', '')
                    if symbol and not is_ascii_symbol(symbol):
                        if symbol not in _warned_symbols:
                            _warned_symbols.add(symbol)
                            logger.warning(f"Filtering non-ASCII symbol: {symbol}")
                        continue
                filtered.append(item)
            if len(filtered) != original_len:
                parsed = filtered
                modified = True
                logger.info(f"Filtered {original_len - len(filtered)} non-ASCII entries from list response")

        # Handle dict response (e.g., /account)
        elif isinstance(parsed, dict):
            # Filter 'positions' array
            if 'positions' in parsed and isinstance(parsed['positions'], list):
                original_len = len(parsed['positions'])
                filtered = []
                for item in parsed['positions']:
                    if isinstance(item, dict):
                        symbol = item.get('symbol', '')
                        if symbol and not is_ascii_symbol(symbol):
                            if symbol not in _warned_symbols:
                                _warned_symbols.add(symbol)
                                logger.warning(f"Filtering non-ASCII symbol from positions: {symbol}")
                            continue
                    filtered.append(item)
                if len(filtered) != original_len:
                    parsed['positions'] = filtered
                    modified = True
                    logger.info(f"Filtered {original_len - len(filtered)} non-ASCII positions")

        if modified:
            # Re-encode to JSON bytes
            return json.dumps(parsed, ensure_ascii=False).encode('utf-8')
        else:
            return data

    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        # If parsing fails, return original data
        logger.debug(f"Could not parse response as JSON: {e}")
        return data
    except Exception as e:
        logger.error(f"Error filtering response: {e}")
        return data


def apply_position_filter_patch() -> bool:
    """
    Apply patch to filter non-ASCII symbols from Binance responses.

    This patches aiohttp.ClientResponse.read() to intercept raw bytes
    and filter non-ASCII symbols BEFORE msgspec/Rust parsing.

    Returns
    -------
    bool
        True if patch was applied successfully.
    """
    global _position_patch_applied

    if _position_patch_applied:
        logger.debug("Position filter patch already applied")
        return True

    if not AIOHTTP_AVAILABLE:
        logger.error(
            "❌ Cannot apply position filter patch: aiohttp is not installed.\n"
            "   This is required to filter non-ASCII symbols like '币安人生USDT'.\n"
            "   Install with: pip install aiohttp"
        )
        return False

    try:
        # Store original read method
        original_read = aiohttp.ClientResponse.read

        @wraps(original_read)
        async def filtered_read(self):
            """Wrapper that filters non-ASCII symbols from Binance responses."""
            data = await original_read(self)

            # Only process Binance Futures API responses
            url = str(self.url)
            if 'fapi.binance.com' in url or 'dapi.binance.com' in url:
                # Filter position-related endpoints
                if '/positionRisk' in url or '/account' in url or '/v2/account' in url:
                    # Check content type
                    content_type = self.headers.get('Content-Type', '')
                    if 'application/json' in content_type:
                        data = filter_non_ascii_from_json_bytes(data, url)

            return data

        # Apply the patch
        aiohttp.ClientResponse.read = filtered_read

        _position_patch_applied = True
        logger.info("✅ Patched aiohttp.ClientResponse.read() for non-ASCII symbol filtering")
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
    print("✅ ASCII check works")

    # Test filter_non_ascii_from_json_bytes - list
    test_list = [
        {"symbol": "BTCUSDT", "positionAmt": "1.0"},
        {"symbol": "币安人生USDT", "positionAmt": "0"},
        {"symbol": "ETHUSDT", "positionAmt": "2.0"},
    ]
    test_bytes = json.dumps(test_list).encode('utf-8')
    filtered_bytes = filter_non_ascii_from_json_bytes(test_bytes, "test")
    filtered_list = json.loads(filtered_bytes)
    assert len(filtered_list) == 2
    assert filtered_list[0]["symbol"] == "BTCUSDT"
    assert filtered_list[1]["symbol"] == "ETHUSDT"
    print("✅ List filter works")

    # Test filter_non_ascii_from_json_bytes - dict with positions
    test_dict = {
        "totalMarginBalance": "1000",
        "positions": [
            {"symbol": "BTCUSDT", "positionAmt": "1.0"},
            {"symbol": "币安人生USDT", "positionAmt": "0"},
        ]
    }
    test_bytes = json.dumps(test_dict).encode('utf-8')
    filtered_bytes = filter_non_ascii_from_json_bytes(test_bytes, "test")
    filtered_dict = json.loads(filtered_bytes)
    assert len(filtered_dict["positions"]) == 1
    assert filtered_dict["positions"][0]["symbol"] == "BTCUSDT"
    print("✅ Dict filter works")

    print("✅ All tests passed!")
