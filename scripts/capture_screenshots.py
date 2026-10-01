"""Capture the actual running dashboard for README illustrations using headless Chromium.

Start scripts/dev.py first. Install a browser via `playwright install chromium`, or pass
`--channel msedge` / `--channel chrome` to use an existing browser installation.
"""

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", default=None)
    parser.add_argument("--url", default="http://127.0.0.1:8501")
    args = parser.parse_args()
    out = Path(__file__).resolve().parents[1] / "docs" / "screenshots"
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel=args.channel)
        page = browser.new_page(viewport={"width": 1600, "height": 1800}, device_scale_factor=1)
        page.goto(args.url)
        page.get_by_role("heading", name="Cross-Channel Overview", exact=True).wait_for(timeout=30000)
        page.get_by_text("Campaigns at a glance", exact=True).wait_for()
        page.locator('[data-testid="stMetricValue"]').first.wait_for()
        page.wait_for_timeout(2500)
        page.screenshot(path=str(out / "overview.png"), full_page=True)
        for section, filename in [
            ("Campaign Health", "health"),
            ("Recommendations", "recommendations"),
            ("Budget Simulator", "budget"),
        ]:
            page.get_by_text(section, exact=True).first.click()
            page.get_by_role("heading", name=section, exact=True).wait_for()
            if section == "Campaign Health":
                page.get_by_text("Evidence and uncertainty", exact=True).wait_for()
                page.locator('[data-testid="stSelectbox"]').filter(
                    has=page.get_by_text("Inspect campaign", exact=True)
                ).get_by_role("combobox").click()
                page.get_by_text("Google | Revenue Analytics | Landing mismatch", exact=True).last.click()
                page.get_by_text(
                    "Ad promise and landing-page proposition do not align", exact=False
                ).wait_for()
            elif section == "Recommendations":
                page.get_by_text("Record human decision", exact=True).wait_for()
                page.locator('[data-testid="stSelectbox"]').filter(
                    has=page.get_by_text("Review recommendation", exact=True)
                ).get_by_role("combobox").click()
                page.get_by_text("Google Ads · G03 · Change landing page · Proposed", exact=True).click()
                page.get_by_text("Landing-page mismatch is reducing conversion rate.", exact=False).wait_for()
            else:
                page.get_by_text("Reallocated", exact=True).wait_for()
            # Wait for rendering/requests rather than photographing the previous page's content.
            page.wait_for_timeout(1500)
            page.screenshot(path=str(out / f"{filename}.png"), full_page=True)
        browser.close()
    print(f"Captured screenshots in {out}")


if __name__ == "__main__":
    main()
