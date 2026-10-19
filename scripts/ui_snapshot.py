#!/usr/bin/env python3
"""Capture the CorteX demo console states at the two target viewport sizes."""

from __future__ import annotations

import asyncio
from pathlib import Path

from playwright.async_api import Page, async_playwright


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "ui_snapshots"
BASE_URL = "http://localhost:8080/?demo=1"


async def _wait(page: Page) -> None:
    await page.wait_for_timeout(800)


async def _shot(page: Page, stem: str, width: int, height: int) -> None:
    await _wait(page)
    await page.screenshot(
        path=OUTPUT_DIR / f"{stem}_{width}x{height}.png",
        full_page=False,
    )


async def capture(width: int, height: int, browser) -> None:
    page = await browser.new_page(viewport={"width": width, "height": height})
    browser_errors: list[str] = []
    page.on(
        "console",
        lambda message: browser_errors.append(message.text)
        if message.type == "error"
        else None,
    )
    page.on("pageerror", lambda error: browser_errors.append(str(error)))
    await page.goto(BASE_URL, wait_until="networkidle")
    await page.wait_for_function("window.cortexDemo !== undefined")
    await page.wait_for_selector('#ar-canvas[data-ready="true"]')
    procedure = await page.evaluate(
        "async () => (await (await fetch('/api/case')).json()).patient.procedure.value"
    )

    await _shot(page, "01_initial", width, height)

    await page.evaluate("window.cortexDemo.say('surgeon', 'Brief me on this patient')")
    await page.evaluate("window.cortexDemo.call('display_all_patient_data', {})")
    await page.evaluate("window.cortexDemo.call('get_tumor_measurements', {})")
    await page.evaluate("window.cortexDemo.call('get_surgical_phase', {phase: 'positioning'})")
    await page.evaluate("window.cortexDemo.say('cortex', 'Forty-six-year-old male…')")
    await _shot(page, "02_patient", width, height)

    await page.evaluate("window.cortexDemo.call('check_drug_safety', {drug_name: 'cefazolin'})")
    await _shot(page, "03_drug", width, height)

    await page.evaluate("window.cortexDemo.call('hide_all_overlays', {})")
    await page.evaluate(
        "window.cortexDemo.call('log_event', "
        "{event_type: 'timeout_complete', note: 'WHO time-out verified'})"
    )
    await page.evaluate(
        "procedure => window.cortexDemo.call('show_agent_summary', {"
        "title: 'WHO Surgical Safety Checklist', content: '', bullets: ["
        "'Patient: 46-year-old male', `Procedure: ${procedure}`, "
        "'Allergies: Cefazolin (hives), Latex', 'Essential imaging displayed']})",
        procedure,
    )
    await _shot(page, "04_timeout", width, height)

    await page.evaluate("window.cortexDemo.call('hide_all_overlays', {})")
    await page.evaluate("window.cortexDemo.call('rotate_model', {axis: 'x', degrees: 90})")
    await page.evaluate(
        "window.cortexDemo.call('toggle_structure', {structure: 'edema', visible: false})"
    )
    await _shot(page, "05_3d", width, height)

    await page.evaluate("window.cortexDemo.call('show_only_ar', {})")
    await _shot(page, "06_only3d", width, height)

    await page.close()
    if browser_errors:
        details = "\n".join(browser_errors)
        raise RuntimeError(f"Browser errors at {width}x{height}:\n{details}")


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            for width, height in ((1920, 1080), (1366, 768)):
                await capture(width, height, browser)
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
