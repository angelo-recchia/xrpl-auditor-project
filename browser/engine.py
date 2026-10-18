import asyncio
from playwright.async_api import async_playwright

class HermesBrowserEngine:
    def __init__(self, headless: bool = False):
        self.headless = headless

    async def inspect_vault_ui(self, target_url: str):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context()
            page = await context.new_page()
            print(f"Navegando a la dApp: {target_url}")
            await page.goto(target_url)
            await page.wait_for_timeout(3000)
            page_title = await page.title()
            print(f"Título de la página detectado: {page_title}")
            await browser.close()
            return page_title

if __name__ == "__main__":
    import sys
    # Soporta pasar la URL por argumento CLI o usar fallback activo
    demo_url = sys.argv[1] if len(sys.argv) > 1 else "https://devnet.xrpl.org"
    engine = HermesBrowserEngine(headless=False)
    asyncio.run(engine.inspect_vault_ui(demo_url))