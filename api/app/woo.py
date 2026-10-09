"""Minimal read-only WooCommerce REST client (spec: read-only keys, paginated)."""
import httpx


class WooClient:
    def __init__(self, base_url: str, key: str, secret: str, transport: httpx.BaseTransport | None = None):
        self._http = httpx.Client(
            base_url=base_url.rstrip("/") + "/wp-json/wc/v3", auth=(key, secret),
            timeout=60, transport=transport)

    def pages(self, path: str, **params):
        """Yield every item of a paginated collection."""
        page = 1
        while True:
            r = self._http.get(path, params={**params, "per_page": 100, "page": page})
            r.raise_for_status()
            yield from r.json()
            if page >= int(r.headers.get("X-WP-TotalPages", 1)):
                return
            page += 1

    def get(self, path: str, **params):
        r = self._http.get(path, params=params)
        r.raise_for_status()
        return r.json()
