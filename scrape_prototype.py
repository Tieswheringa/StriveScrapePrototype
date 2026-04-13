def run_scraper(credentials: dict, drempel: int, log_fn, progress_fn, result_fn):
    """Voert de volledige scrape uit. Roept callbacks aan voor UI-updates."""
    from playwright.sync_api import sync_playwright

    def log(msg):
        log_fn(msg)

    TEST_MODE = True
    TEST_AANTAL = 1  # zet op bv 5 voor vijf opdrachten, of False bovenaan voor alles

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ]
        )

        page_striive = browser.new_page(viewport={"width": 1280, "height": 800})
        page_tool = browser.new_page(viewport={"width": 1280, "height": 800})

        page_striive.on("crash", lambda: log("💥 Striive page crash gedetecteerd"))
        page_tool.on("crash", lambda: log("💥 Tool page crash gedetecteerd"))
        page_striive.on("close", lambda: log("📕 Striive page gesloten"))
        page_tool.on("close", lambda: log("📕 Tool page gesloten"))
        browser.on("disconnected", lambda: log("🔌 Browser disconnected"))

        # ── Inloggen op Striive ──────────────────────────────────────────────
        log("🔐 Inloggen op Striive...")
        page_striive.goto("https://login.striive.com/", wait_until="domcontentloaded", timeout=60000)
        page_striive.wait_for_timeout(3000)

        email_selectors = [
            'input[type="email"]',
            'input[name="email"]',
            '#email',
            'input[id="email"]',
            'input[placeholder*="mail" i]',
            'input[autocomplete="email"]',
            'input[autocomplete="username"]',
        ]

        email_veld = None
        for sel in email_selectors:
            try:
                el = page_striive.locator(sel).first
                el.wait_for(state="visible", timeout=5000)
                email_veld = el
                log(f"  ✔ E-mailveld gevonden: {sel}")
                break
            except:
                continue

        if email_veld is None:
            page_striive.screenshot(path="/tmp/debug_login.png", full_page=True)
            raise Exception("E-mailveld niet gevonden. Screenshot opgeslagen in /tmp/debug_login.png")

        email_veld.click()
        email_veld.fill(credentials["email"])

        ww_veld = page_striive.locator('input[type="password"]').first
        ww_veld.wait_for(state="visible", timeout=10000)
        ww_veld.click()
        ww_veld.fill(credentials["wachtwoord"])

        login_selectors = [
            'button:has-text("Login")',
            'button:has-text("Inloggen")',
            'button[type="submit"]',
            'input[type="submit"]',
        ]

        for sel in login_selectors:
            try:
                knop = page_striive.locator(sel).first
                knop.wait_for(state="visible", timeout=4000)
                knop.click()
                log(f"  ✔ Login-knop geklikt ({sel})")
                break
            except:
                continue
        else:
            ww_veld.press("Enter")
            log("  ℹ️ Login-knop niet gevonden, Enter gebruikt.")

        try:
            page_striive.wait_for_selector('text=Overzicht', timeout=30000)
        except:
            page_striive.wait_for_url("**/dashboard**", timeout=30000)

        log("✅ Ingelogd op Striive.")

        # ── Naar opdrachtenpagina ─────────────────────────────────────────────
        try:
            page_striive.click('a:has-text("Opdrachten")', timeout=10000)
        except:
            page_striive.goto("https://supplier.striive.com/job-requests", timeout=60000)

        page_striive.wait_for_selector('[data-testid="jobRequestListItem"]', timeout=30000)
        page_striive.wait_for_timeout(2000)
        log("✅ Opdrachtenpagina geladen.")

        # ── Alle opdracht-URLs verzamelen ────────────────────────────────────
        log("🔍 Alle opdracht-URLs verzamelen via scrollen...")
        alle_urls = []
        gevonden_set = set()
        scroll_stap, scroll_pos = 150, 0
        geen_nieuw, max_geen_nieuw = 0, 8

        while geen_nieuw < max_geen_nieuw:
            items = page_striive.locator('[data-testid="jobRequestListItem"]').all()
            voor = len(gevonden_set)

            for item in items:
                try:
                    href = item.get_attribute('href')
                    if not href:
                        href = item.locator('a').first.get_attribute('href')

                    if href and href not in gevonden_set:
                        gevonden_set.add(href)
                        if href.startswith('/'):
                            href = 'https://supplier.striive.com' + href
                        alle_urls.append(href)
                except:
                    pass

            scroll_pos += scroll_stap
            res = page_striive.evaluate(f"""
                () => {{
                    const s = document.querySelector('div.p-scroller');
                    if (s) {{
                        s.scrollTop = {scroll_pos};
                        return {{
                            scrollTop: s.scrollTop,
                            scrollHeight: s.scrollHeight,
                            clientHeight: s.clientHeight
                        }};
                    }}
                    return {{scrollTop:0, scrollHeight:0, clientHeight:0}};
                }}
            """)
            page_striive.wait_for_timeout(1000)

            geen_nieuw = 0 if len(gevonden_set) > voor else geen_nieuw + 1

            max_scroll = res['scrollHeight'] - res['clientHeight']
            if max_scroll > 0 and res['scrollTop'] >= max_scroll - 10:
                log(f"📋 Einde van lijst bereikt. Totaal gevonden: {len(alle_urls)}")
                break

        if TEST_MODE:
            alle_urls = alle_urls[:TEST_AANTAL]
            log(f"🧪 TESTMODE actief: {len(alle_urls)} opdracht(en) worden verwerkt.")

        log(f"📋 Start analyse van {len(alle_urls)} opdracht(en).")

        # ── CV-tool openen (één keer) ────────────────────────────────────────
        log("🌐 CV-tool openen...")
        page_tool.goto(
            "https://inthearenabv-cv-tool.streamlit.app/",
            wait_until="domcontentloaded",
            timeout=60000
        )
        page_tool.wait_for_timeout(5000)

        frame = page_tool.frame_locator("iframe").first

        try:
            frame.locator("body").wait_for(timeout=30000)
            log("✅ Iframe geladen.")
        except Exception as e:
            raise Exception(f"Iframe van CV-tool niet geladen: {e}")

        # Login op CV-tool indien nodig
        try:
            pw = frame.locator('input[type="password"]').first
            if pw.is_visible(timeout=5000):
                pw.fill(credentials["streamlit_pw"])
                frame.locator('button:has-text("Log in")').first.click()
                page_tool.wait_for_timeout(5000)
                log("🔑 Ingelogd op CV-tool.")
        except Exception as e:
            log(f"ℹ️ Geen CV-tool login nodig of loginveld niet zichtbaar: {e}")

        # Ga naar juiste scherm
        try:
            knop_test = frame.locator('button:has-text("Test geschiktheid opdracht")').first
            if knop_test.is_visible(timeout=8000):
                knop_test.click()
                page_tool.wait_for_timeout(4000)
                log("📄 Naar 'Test geschiktheid opdracht' gegaan.")
        except Exception as e:
            log(f"ℹ️ Knop 'Test geschiktheid opdracht' niet gevonden of al op juiste pagina: {e}")

        alle_matches = []

        # ── Verwerk opdrachten ───────────────────────────────────────────────
        for i, url in enumerate(alle_urls):
            progress_fn(i + 1, len(alle_urls))
            log(f"\n[{i+1}/{len(alle_urls)}] {url}")

            try:
                page_striive.goto(url, wait_until="domcontentloaded", timeout=60000)
                page_striive.wait_for_timeout(2000)
                tekst = page_striive.locator('app-job-request-details').inner_text(timeout=15000)
            except Exception as e:
                log(f"  ⚠️ Kon opdrachtdetails niet laden: {e}")
                continue

            uurtarief = extraheer_uurtarief(tekst)
            startdatum = extraheer_startdatum(tekst)
            deadline = extraheer_reageer_deadline(tekst)
            log(f"  💶 {uurtarief} | 📅 {startdatum} | ⏰ {deadline}")

            # Zorg dat textarea zichtbaar is
            try:
                ta = frame.locator("textarea").first
                ta.wait_for(state="visible", timeout=30000)
                ta.fill("")
                ta.fill(tekst)
                log("  ✅ Tekst ingevuld in textarea.")
            except Exception as e:
                log(f"  ⚠️ Kon tekst niet invullen: {e}")
                try:
                    body_text = frame.locator("body").inner_text(timeout=5000)
                    log(f"  DEBUG iframe inhoud:\n{body_text[:1500]}")
                except:
                    pass
                try:
                    page_tool.screenshot(path=f"/tmp/tool_debug_{i+1}.png", full_page=True)
                    log(f"  📸 Screenshot opgeslagen: /tmp/tool_debug_{i+1}.png")
                except:
                    pass
                continue

            page_tool.wait_for_timeout(2000)

            try:
                frame.locator('button:has-text("Analyseer geschiktheid")').first.click(timeout=10000)
                log("  ⏳ Analyse gestart...")
            except Exception as e:
                log(f"  ⚠️ Kon analyseknop niet klikken: {e}")
                continue

            try:
                frame.locator('text=Resultaten').wait_for(timeout=120000)
                page_tool.wait_for_timeout(3000)
            except Exception as e:
                log(f"  ⚠️ Resultaten niet gevonden: {e}")
                continue

            n_exp = frame.locator('[data-testid="stExpander"]').count()
            log(f"  📦 {n_exp} expanders gevonden.")

            for j in range(n_exp):
                try:
                    blok = frame.locator('[data-testid="stExpander"]').nth(j)

                    try:
                        blok.locator('summary, [data-testid="stExpanderToggleIcon"], button').first.click(timeout=5000)
                        page_tool.wait_for_timeout(800)
                    except:
                        pass

                    blok_tekst = blok.inner_text(timeout=15000)
                except:
                    continue

                score_m = re.search(r'(\d+)/100', blok_tekst)
                if not score_m:
                    continue

                score = int(score_m.group(1))
                naam_m = re.search(r'[🟢🟡🔴]\s*(.*?)\s*—\s*\d+/100', blok_tekst)
                naam = naam_m.group(1).strip() if naam_m else "onbekend"

                log(f"  👤 {naam} → {score}/100")

                if score > drempel:
                    alle_matches.append({
                        "opdracht": f"Opdracht {i+1}",
                        "naam": naam,
                        "score": score,
                        "uurtarief": uurtarief,
                        "startdatum": startdatum,
                        "deadline": deadline,
                        "url": url,
                    })
                    log(f"  ✅ Match! {naam} ({score}/100) boven drempel {drempel}.")
                    result_fn(alle_matches)

        browser.close()
        log(f"\n🏁 Klaar! {len(alle_matches)} matches gevonden.")
        return alle_matches
