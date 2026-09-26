"""Browser smoke: atmospheric themes, living motion, OpenFreeMap regression."""

from __future__ import annotations

import json
import sys

from playwright.sync_api import sync_playwright

PAGES = [
    ("/", "sunrise", ".atm-clouds .atm-drift"),
    ("/weather/", "cloudy", ".atm-clouds .atm-drift"),
    ("/alerts/", "storm", ".atm-clouds .atm-drift"),
    ("/radar/", "sunset", ".atm-clouds .atm-drift"),
    ("/nowcasting/", "night", ".atm-stars .atm-drift"),
]


def sample_motion(page, selector: str) -> dict:
    t0 = page.evaluate(
        """(sel) => {
          const el = document.querySelector(sel);
          if (!el) return null;
          const cs = getComputedStyle(el);
          return { transform: cs.transform, animation: cs.animationName, opacity: cs.opacity };
        }""",
        selector,
    )
    page.wait_for_timeout(1800)
    t1 = page.evaluate(
        """(sel) => {
          const el = document.querySelector(sel);
          if (!el) return null;
          const cs = getComputedStyle(el);
          return { transform: cs.transform, animation: cs.animationName, opacity: cs.opacity };
        }""",
        selector,
    )
    moving = bool(
        t0 and t1 and t0.get("transform") and t0["transform"] != t1.get("transform")
    )
    has_anim = bool(t0 and t0.get("animation") and t0["animation"] not in ("none", ""))
    return {"t0": t0, "t1": t1, "transform_changed": moving, "has_animation": has_anim}


def main() -> int:
    results = []
    ok = True
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        for path, theme, motion_sel in PAGES:
            blocked = []

            def on_response(resp, blocked=blocked):
                url = resp.url
                if resp.status in (401, 403) and any(
                    x in url for x in ("tile", "openfreemap", "openstreetmap", "carto")
                ):
                    blocked.append(f"{resp.status} {url}")

            page.on("response", on_response)
            page.goto(
                f"http://127.0.0.1:8000{path}",
                wait_until="domcontentloaded",
                timeout=90000,
            )
            page.wait_for_timeout(1500)
            body_class = page.locator("body").get_attribute("class") or ""
            theme_ok = f"theme-{theme}" in body_class
            has_atm = page.locator("#atmospheric-background").count() > 0
            drifts = page.locator(".atm-drift").count()
            content = page.content()
            motion = sample_motion(page, motion_sel)
            item = {
                "path": path,
                "expected_theme": theme,
                "theme_ok": theme_ok,
                "has_atmosphere": has_atm,
                "drift_nodes": drifts,
                "motion": motion,
                "body_class": body_class,
                "osm": "tile.openstreetmap.org" in content,
                "carto": "cartocdn" in content.lower(),
                "blocked": blocked[:3],
            }
            if path == "/alerts/":
                item["storm_rain_opacity"] = page.evaluate(
                    "getComputedStyle(document.querySelector('.atm-rain')).opacity"
                )
                item["has_moon"] = page.locator(".atm-moon").count() > 0
            if path == "/nowcasting/":
                item["moon_opacity"] = page.evaluate(
                    "getComputedStyle(document.querySelector('.atm-moon')).opacity"
                )
                item["stars_opacity"] = page.evaluate(
                    "getComputedStyle(document.querySelector('.atm-stars')).opacity"
                )
            if path == "/":
                item["orb_opacity"] = page.evaluate(
                    "getComputedStyle(document.querySelector('.atm-orb')).opacity"
                )
            if path in {"/", "/radar/"}:
                page.wait_for_timeout(3500)
                item["map_canvas"] = page.locator("#india-map canvas").count()
                item["markers"] = page.locator(".temp-label").count()
                item["openfreemap"] = "openfreemap.org" in content
                if (
                    item["map_canvas"] < 1
                    or item["osm"]
                    or item["carto"]
                    or item["blocked"]
                ):
                    ok = False
            if (
                not theme_ok
                or not has_atm
                or item["osm"]
                or item["carto"]
                or drifts < 5
                or not motion.get("has_animation")
                or not motion.get("transform_changed")
            ):
                ok = False
            results.append(item)
            page.remove_listener("response", on_response)

        page.goto(
            "http://127.0.0.1:8000/", wait_until="domcontentloaded", timeout=90000
        )
        page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.4)")
        page.wait_for_timeout(500)
        scroll = page.evaluate(
            "getComputedStyle(document.documentElement).getPropertyValue('--atm-scroll').trim()"
        )
        results.append({"scroll_progress": scroll})
        print(json.dumps({"ok": ok, "results": results}, indent=2))
        browser.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
