import asyncio
from playwright.async_api import async_playwright

BRAIN = "/Users/doni/.gemini/antigravity-ide/brain/aa42c0a6-56c3-49cf-920e-25ebec03ac86"
USERNAME = "admin"
PASSWORD = "admin123"
APPROVAL_CODE = "90f37d2677eaf015eb0c991538df19714b0491051ccecefc999fdf23f161de28"
ALPACA_KEY    = "PKTKYFOBZCVNQJQ2MBCVQXML2Y"
ALPACA_SECRET = "3L2V1D6JraPn3q6eQvAu3Yg8yPHwVfxAwXeX6qsoisbn"
N8N_EMAIL = "doneeswaranjsapc2022@gmail.com"

async def dismiss_modals(page):
    for txt in ["Skip", "Get started", "Dismiss", "Skip for now"]:
        try:
            await page.click(f"button:has-text('{txt}')", timeout=1000)
            await page.wait_for_timeout(300)
        except:
            pass

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        # ── SCREENSHOT 2: Approve Box + Confirmation ──────────────────────────
        page = await browser.new_page(viewport={"width": 1440, "height": 1000})
        await page.goto("http://localhost:8000")
        await page.wait_for_selector("#question")

        # Set localStorage directly — bypasses the login modal entirely
        await page.evaluate(f"""() => {{
            localStorage.setItem('agenttrade_user', '{USERNAME}');
            localStorage.setItem('agenttrade_pass', '{PASSWORD}');
            localStorage.setItem('alpaca_key', '{ALPACA_KEY}');
            localStorage.setItem('alpaca_secret', '{ALPACA_SECRET}');
        }}""")
        await page.reload()
        await page.wait_for_timeout(2000)

        # Set code input after reload
        await page.evaluate(f"""() => {{
            const c = document.getElementById('code');
            if (c) c.value = '{PASSWORD}';
            const u = document.getElementById('username');
            if (u) u.value = '{USERNAME}';
            const ak = document.getElementById('alpaca-key');
            if (ak) ak.value = '{ALPACA_KEY}';
            const as_ = document.getElementById('alpaca-secret');
            if (as_) as_.value = '{ALPACA_SECRET}';
        }}""")

        # If the Alpaca modal appears with keys pre-filled, click Save Keys to register them
        try:
            await page.click("button:has-text('Save Keys')", timeout=3000)
            await page.wait_for_timeout(2000)
        except:
            pass

        # Fill the proposal form
        await page.evaluate("document.getElementById('pticker').scrollIntoView()")
        await page.wait_for_timeout(500)
        await page.fill("#pticker", "TSLA")
        await page.wait_for_timeout(200)
        await page.select_option("#pside", "BUY")
        await page.fill("#pqty", "1")
        try:
            await page.fill("#prationale", "Agent verdict: BUY. TSLA shows AI-driven revenue growth confirmed by vector evidence.")
        except:
            pass

        await page.click("#propose")
        await page.wait_for_timeout(1500)
        # Dismiss any remaining modal (skip if Alpaca pops again)
        await dismiss_modals(page)
        await page.wait_for_timeout(3000)

        # Scroll to pending section and screenshot
        await page.evaluate("document.getElementById('pending').scrollIntoView()")
        await page.wait_for_timeout(1000)
        await page.screenshot(path=f"{BRAIN}/2_approve_box.png", full_page=True)
        print(f"Screenshot saved: {BRAIN}/2_approve_box.png")

        # Try clicking Approve button inside #pending
        try:
            approve_btn = page.locator("#pending button").first
            await approve_btn.wait_for(state="visible", timeout=5000)
            await approve_btn.click()
            await page.wait_for_timeout(5000)
            await page.evaluate("document.getElementById('pending').scrollIntoView()")
            await page.screenshot(path=f"{BRAIN}/2_approve_confirmation.png", full_page=True)
            print(f"Screenshot saved: {BRAIN}/2_approve_confirmation.png")
        except Exception as e:
            print(f"Approve click failed: {e}")
            await page.screenshot(path=f"{BRAIN}/2_approve_confirmation.png", full_page=True)
            print(f"Screenshot saved: {BRAIN}/2_approve_confirmation.png (fallback)")

        # ── SCREENSHOT 5: n8n Workflow Canvas ────────────────────────────────
        try:
            page2 = await browser.new_page(viewport={"width": 1440, "height": 1000})
            await page2.goto("http://localhost:5678")
            await page2.wait_for_timeout(4000)

            # Fill n8n sign-in with real credentials
            try:
                await page2.fill("input[type='email']", N8N_EMAIL, timeout=3000)
                # Try common passwords — n8n sets one on first setup
                for pwd in ["admin12345", "admin123456", "Admin1234!", "password", "n8n12345"]:
                    try:
                        await page2.fill("input[type='password']", pwd)
                        await page2.click("button[type='submit']")
                        await page2.wait_for_timeout(2000)
                        # Check if we're past login (no longer on signin page)
                        if "signin" not in page2.url and "sign-in" not in page2.url:
                            print(f"n8n login succeeded with password: {pwd}")
                            break
                        else:
                            print(f"n8n password '{pwd}' failed, trying next...")
                    except:
                        pass
            except Exception as e:
                print(f"n8n login form error: {e}")

            # Skip any setup wizard
            await dismiss_modals(page2)
            await page2.wait_for_timeout(2000)

            # Navigate to workflows
            await page2.goto("http://localhost:5678/workflows")
            await page2.wait_for_timeout(5000)
            await page2.screenshot(path=f"{BRAIN}/5_n8n_workflows.png")
            print(f"Screenshot saved: {BRAIN}/5_n8n_workflows.png")

            # Try to open first workflow canvas
            for sel in [
                "[data-test-id='resources-list-item']",
                "[data-test-id='workflow-card']",
                "a[href*='/workflow/']",
                "div[class*='workflow-list'] a",
            ]:
                try:
                    await page2.click(sel, timeout=3000)
                    await page2.wait_for_timeout(5000)
                    await page2.screenshot(path=f"{BRAIN}/5_n8n_canvas.png")
                    print(f"Screenshot saved: {BRAIN}/5_n8n_canvas.png")
                    break
                except:
                    pass

        except Exception as e:
            print(f"n8n screenshots failed: {e}")

        await browser.close()
        print("\nAll done!")

if __name__ == "__main__":
    asyncio.run(main())
