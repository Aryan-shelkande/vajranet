"""Browser smoke check for OpenFreeMap basemap."""

from __future__ import annotations

import json
import sys

from playwright.sync_api import sync_playwright


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        blocked: list[str] = []
        tile_ok = 0

        def on_response(resp):
            nonlocal tile_ok
            url = resp.url
            if "openfreemap.org" in url and resp.status == 200:
                tile_ok += 1
            if resp.status in (401, 403) and any(
                x in url for x in ("tile", "openfreemap", "openstreetmap", "carto")
            ):
                blocked.append(f"{resp.status} {url}")

        page.on("response", on_response)
        page.goto("http://127.0.0.1:8000/", wait_until="networkidle", timeout=90000)
        page.locator("#map-section").scroll_into_view_if_needed()
        page.wait_for_timeout(6000)
        page.screenshot(path="map_verify.png", full_page=False)

        markers = page.locator(".temp-label").count()
        canvas = page.locator("#india-map canvas").count()
        attr = ""
        if page.locator(".leaflet-control-attribution").count():
            attr = page.locator(".leaflet-control-attribution").inner_text()
        content = page.content()
        out = {
            "markers": markers,
            "canvas": canvas,
            "attribution": attr,
            "openfreemap_ok_responses": tile_ok,
            "map_error_visible": page.locator("#map-error.visible").count() > 0,
            "blocked": blocked[:5],
            "osm_raster": "tile.openstreetmap.org" in content,
            "carto": "cartocdn" in content.lower(),
            "has_openfreemap_config": "tiles.openfreemap.org/styles/liberty" in content,
        }
        print(json.dumps(out, indent=2))
        browser.close()

        ok = (
            markers > 0
            and canvas > 0
            and tile_ok > 0
            and not blocked
            and not out["osm_raster"]
            and not out["carto"]
            and "OpenFreeMap" in attr
            and not out["map_error_visible"]
        )
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
