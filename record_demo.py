import asyncio
import os
import glob
from playwright.async_api import async_playwright

async def run():
    os.makedirs("demo_raw", exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            record_video_dir="demo_raw",
            record_video_size={"width": 1280, "height": 720}
        )
        page = await context.new_page()
        
        print("Navigating to http://localhost:8080...")
        await page.goto("http://localhost:8080")
        await page.wait_for_selector("#input", timeout=10000)
        await asyncio.sleep(2)

        # 1. First prompt: Core app strength (Pantry recipe recommendation)
        prompt1 = "I have chicken breast, garlic, heavy cream, spinach, and pasta. What recipe do you suggest?"
        print(f"Typing Prompt 1: {prompt1}")
        for char in prompt1:
            await page.type("#input", char, delay=35)
        await asyncio.sleep(0.5)
        await page.click("button[type='submit']")

        print("Waiting for response to Prompt 1...")
        await asyncio.sleep(8)

        # 2. Second prompt: Richer prompt showing off Omni video generation tool call
        prompt2 = "Can you generate a short cooking video of searing garlic Tuscan chicken in a skillet?"
        print(f"Typing Prompt 2: {prompt2}")
        for char in prompt2:
            await page.type("#input", char, delay=35)
        await asyncio.sleep(0.5)
        await page.click("button[type='submit']")

        print("Waiting for response to Prompt 2 (video generation)...")
        await asyncio.sleep(15)

        print("Closing context and saving video...")
        await context.close()
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
