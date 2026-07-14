"""
Low-level Binance HTTP client with retry/backoff.

This is the ONLY code in the repo that makes HTTP requests to Binance.
v7/ and alphaforge/ must NOT import or call this directly — they go
through BinanceMarketDataService instead.
"""

import time
import logging
from typing import Any, Optional
from urllib.parse import urljoin

import requests

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.binance.com"
_FUTURES_BASE_URL = "https://fapi.binance.com"


class BinanceClientError(Exception):
    """Raised on Binance API errors (non-2xx or parse failures).

    Attributes:
        status_code: HTTP status code if available (e.g. 429 for rate limit).
        response_body: Raw response text if available.
    """

    def __init__(
        self,
        message: str = "",
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class BinanceClient:
    """Thin wrapper around Binance REST API.

    Only handles HTTP transport, retry, and response parsing.
    No caching, no normalization, no business logic.
    """

    def __init__(
        self,
        base_url: str = _BASE_URL,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        retry_delay_seconds: float = 1.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._retry_delay = retry_delay_seconds
        self._session = requests.Session()

    # ------------------------------------------------------------------
    # Public endpoints
    # ------------------------------------------------------------------

    def get_klines(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 1000,
    ) -> list[list[Any]]:
        """Fetch klines from Binance.

        Returns raw response data (list of lists). Use KlinesService
        for caching, normalization, and schema enforcement.
        """
        params: dict[str, Any] = {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": min(limit, 1000),
        }
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time

        return self._get("/api/v3/klines", params)

    def get_funding_rate(
        self,
        symbol: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 1000,
    ) -> list[list[Any]]:
        """Fetch funding rate history.

        Returns raw response data. Use FundingService for normalization.
        """
        params: dict[str, Any] = {
            "symbol": symbol.upper(),
            "limit": min(limit, 1000),
        }
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time

        return self._get_futures("/fapi/v1/fundingRate", params)

    def get_open_interest_hist(
        self,
        symbol: str,
        period: str = "1h",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 500,
    ) -> list[list[Any]]:
        """Fetch open interest history from Binance Futures.

        Returns raw response data. Use OpenInterestService for normalization.
        Period: "5m","15m","30m","1h","2h","4h","6h","12h","1d".
        Max limit per call is 500.
        """
        params: dict[str, Any] = {
            "symbol": symbol.upper(),
            "period": period,
            "limit": min(limit, 500),
        }
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time

        return self._get_futures("/fapi/v1/openInterestHist", params)

    def get_premium_index_klines(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 1000,
    ) -> list[list[Any]]:
        """Fetch premium index klines from Binance Futures.

        Returns raw response data. Use PremiumIndexService for normalization.
        Shows the premium/discount of mark price vs index price.
        """
        params: dict[str, Any] = {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": min(limit, 1000),
        }
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time

        return self._get_futures("/fapi/v1/premiumIndexKlines", params)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict[str, Any]) -> Any:
        """GET request with retry logic."""
        return self._get_from_base(self._base_url, path, params)

    def _get_futures(self, path: str, params: dict[str, Any]) -> Any:
        """GET a USD-M futures endpoint from Binance's futures host."""
        return self._get_from_base(_FUTURES_BASE_URL, path, params)

    def _get_from_base(self, base_url: str, path: str, params: dict[str, Any]) -> Any:
        """GET with retry logic from the supplied Binance API host."""
        url = urljoin(base_url, path)
        last_exc: Optional[Exception] = None

        for attempt in range(self._max_retries):
            try:
                resp = self._session.get(
                    url,
                    params=params,
                    timeout=self._timeout,
                )
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as e:
                last_exc = e
                status_code = None
                response_body = None
                if e.response is not None:
                    status_code = e.response.status_code
                    try:
                        response_body = e.response.text
                    except Exception:
                        pass
                logger.warning(
                    "Binance GET %s failed (attempt %d/%d): %s",
                    path, attempt + 1, self._max_retries, e,
                )
                if attempt < self._max_retries - 1:
                    time.sleep(self._retry_delay * (2 ** attempt))
                continue

        raise BinanceClientError(
            f"Binance GET {path} failed: {last_exc}",
            status_code=status_code,
            response_body=response_body,
        ) from last_exc
