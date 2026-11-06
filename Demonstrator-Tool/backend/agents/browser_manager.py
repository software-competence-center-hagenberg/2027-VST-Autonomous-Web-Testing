import asyncio
from browser_use import Browser
from browser_use.actor.page import Page
import base64
import os
from pathlib import Path

class BrowserManager:
    def __init__(self):
        width = int(os.getenv("DEMO_BROWSER_WIDTH", "1920"))
        height = int(os.getenv("DEMO_BROWSER_HEIGHT", "1080"))
        left = int(os.getenv("DEMO_BROWSER_LEFT", "0"))
        top = int(os.getenv("DEMO_BROWSER_TOP", "0"))
        headless = os.getenv("DEMO_BROWSER_HEADLESS", "").strip().lower() in {"1", "true", "yes", "on"}
        self.browser = Browser(
            keep_alive=True, 
            headless=headless,
            window_size={"width": width, "height": height},
            # browser-use represents the top-left position as width/height.
            window_position={"width": left, "height": top},
        )
        self.is_started = False
        self._screenshot_lock = asyncio.Lock()

    async def start(self):
        if not self.is_started:
            await self.browser.start()
            self.is_started = True

    async def stop(self):
        if self.is_started:
            await self.browser.stop()
            self.is_started = False

    async def get_browser(self) -> Browser:
        return self.browser
    
    async def goto(self, url: str):
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url
        page = await self.browser.must_get_current_page()
        await page.goto(url)

    async def get_DOM(self) -> str:
        page = await self.browser.must_get_current_page()
        return await page.evaluate("() => document.documentElement.outerHTML")
    
    async def get_stripped_DOM(self) -> str:
        return await self.browser.get_state_as_text()
    
    async def get_URL(self) -> str:
        return await self.browser.get_current_page_url()
    
    async def screenshot(self, path: str):
        async with self._screenshot_lock:
            page = await self.browser.must_get_current_page()
            await self.save_screenshot(page, path)

    async def capture_jpeg(self, quality: int = 65) -> bytes:
        async with self._screenshot_lock:
            page = await self.browser.must_get_current_page()
            encoded = await page.screenshot(format="jpeg", quality=quality)
            return base64.b64decode(encoded)

    async def save_screenshot(self, page:Page, path: str, format: str = "png", quality: int | None = None):
        """
        Takes a screenshot using page.screenshot() and saves it to a file.
        """
        b64_data = await page.screenshot(format=format, quality=quality)
        image_data = base64.b64decode(b64_data)
        
        path_obj = Path(path)
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        path_obj.write_bytes(image_data)