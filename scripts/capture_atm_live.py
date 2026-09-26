"""Fast living-atmosphere motion + screenshot check."""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path("tmp_atm_live")
PAGES = [
    ("/", "overview"),
    ("/weather/", "weather"),
    ("/alerts/", "alerts"),
    ("/radar/", "radar"),
    ("/nowcasting/", "nowcast"),
]


def main() -> None:
    OUT.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.set_default_timeout(90000)
        for path, name in PAGES:
            page.goto(f"http://127.0.0.1:8000{path}?v=live2", wait_until="commit")
            page.wait_for_selector("#atmospheric-background", timeout=45000)
            page.wait_for_timeout(1200)
            page.screenshot(path=str(OUT / f"{name}_desktop.png"), full_page=False)
            t0 = page.evaluate("""() => {
                  const c = document.querySelector('.atm-clouds .atm-drift');
                  const s = document.querySelector('.atm-stars .atm-drift');
                  const el = c || s;
                  return {
                    theme: document.body.dataset.pageTheme,
                    cond: document.body.dataset.atmosphere,
                    transform: el ? getComputedStyle(el).transform : null,
                    anim: el ? getComputedStyle(el).animationName : null,
                    orb: getComputedStyle(document.querySelector('.atm-orb')).opacity,
                    moon: getComputedStyle(document.querySelector('.atm-moon')).opacity,
                    rain: getComputedStyle(document.querySelector('.atm-rain')).opacity,
                    horizon: getComputedStyle(document.querySelector('.atm-horizon')).opacity,
                    drifts: document.querySelectorAll('.atm-drift').length,
                  };
                }""")
            page.wait_for_timeout(1600)
            t1 = page.evaluate("""() => {
                  const c = document.querySelector('.atm-clouds .atm-drift');
                  const s = document.querySelector('.atm-stars .atm-drift');
                  const el = c || s;
                  return el ? getComputedStyle(el).transform : null;
                }""")
            moved = bool(t0.get("transform") and t1 and t0["transform"] != t1)
            print(
                name,
                {
                    **t0,
                    "moved": moved,
                    "t1": (t1 or "")[:48],
                },
            )

        page.set_viewport_size({"width": 390, "height": 844})
        for path, name in [
            ("/", "overview"),
            ("/alerts/", "alerts"),
            ("/nowcasting/", "nowcast"),
        ]:
            page.goto(f"http://127.0.0.1:8000{path}?v=live2", wait_until="commit")
            page.wait_for_selector("#atmospheric-background", timeout=45000)
            page.wait_for_timeout(800)
            page.screenshot(path=str(OUT / f"{name}_mobile.png"), full_page=False)

        page.set_viewport_size({"width": 1440, "height": 900})
        page.goto("http://127.0.0.1:8000/radar/?v=live2", wait_until="commit")
        page.wait_for_selector("#india-map", timeout=45000)
        page.wait_for_timeout(4000)
        zoom = page.locator(".leaflet-control-zoom-in")
        if zoom.count():
            zoom.click()
        page.screenshot(path=str(OUT / "radar_map.png"), full_page=False)
        map_info = page.evaluate("""() => ({
              canvas: !!document.querySelector('#india-map canvas'),
              markers: document.querySelectorAll('.temp-label').length,
              openfreemap: document.documentElement.innerHTML.includes('openfreemap.org'),
              osm: document.documentElement.innerHTML.includes('tile.openstreetmap.org'),
              carto: document.documentElement.innerHTML.toLowerCase().includes('cartocdn'),
            })""")
        print("radar_map", map_info)

        page2 = browser.new_page(
            viewport={"width": 1280, "height": 800}, reduced_motion="reduce"
        )
        page2.goto("http://127.0.0.1:8000/?v=live2", wait_until="commit")
        page2.wait_for_selector("#atmospheric-background", timeout=45000)
        page2.wait_for_timeout(600)
        rm = page2.evaluate("""() => {
              const d = document.querySelector('.atm-clouds .atm-drift');
              return {
                anim: getComputedStyle(d).animationName,
                reduced: document.body.classList.contains('reduced-motion'),
              };
            }""")
        print("reduced", rm)
        browser.close()
    print("shots_ok")


if __name__ == "__main__":
    main()
