import asyncio
import os
from playwright.async_api import async_playwright

async def run():
    os.makedirs("demo_raw", exist_ok=True)
    # Clean previous raw videos
    for f in os.listdir("demo_raw"):
        if f.endswith(".webm"):
            os.remove(os.path.join("demo_raw", f))

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

        # 1. First prompt: Pantry recipe recommendation
        prompt1 = "I have chicken breast, garlic, heavy cream, spinach, and pasta. What recipe do you suggest?"
        print(f"Typing Prompt 1: {prompt1}")
        for char in prompt1:
            await page.type("#input", char, delay=35)
        await asyncio.sleep(0.5)
        await page.click("button[type='submit']")

        print("Waiting for agent response to Prompt 1...")
        # Wait up to 30 seconds for the first agent message bubble to stop showing '…'
        for _ in range(60):
            await asyncio.sleep(0.5)
            agent_bubbles = await page.query_selector_all(".msg.agent .bubble")
            if agent_bubbles:
                txt = await agent_bubbles[0].inner_text()
                if txt.strip() != "…":
                    print(f"Received Prompt 1 response ({len(txt)} chars)!")
                    break
        await asyncio.sleep(4)  # Pause to let user read on video

        # 2. Second prompt: Omni video generation tool call
        prompt2 = "Can you generate a short cooking video of searing garlic Tuscan chicken in a skillet?"
        print(f"Typing Prompt 2: {prompt2}")
        for char in prompt2:
            await page.type("#input", char, delay=35)
        await asyncio.sleep(0.5)
        await page.click("button[type='submit']")

        print("Waiting for agent response to Prompt 2...")
        # Wait up to 45 seconds for the second agent message bubble to stop showing '…'
        for _ in range(90):
            await asyncio.sleep(0.5)
            agent_bubbles = await page.query_selector_all(".msg.agent .bubble")
            if len(agent_bubbles) >= 2:
                txt = await agent_bubbles[1].inner_text()
                if txt.strip() != "…":
                    print(f"Received Prompt 2 response ({len(txt)} chars)!")
                    break
        await asyncio.sleep(5)  # Pause to let video response show clearly on screen

        print("Closing context and saving video...")
        await context.close()
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
