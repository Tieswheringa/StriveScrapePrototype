import os
import re
import io
import time
import subprocess
import sys
from typing import Callable, Dict, List, Optional

import streamlit as st
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

# Schrijfbare locatie op Streamlit Cloud
PLAYWRIGHT_BROWSERS_DIR = "/tmp/pw-browsers"
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = PLAYWRIGHT_BROWSERS_DIR


@st.cache_resource(show_spinner="Playwright-browsers installeren (eenmalig)...")
def installeer_playwright():
    os.makedirs(PLAYWRIGHT_BROWSERS_DIR, exist_ok=True)

    try:
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True,
            text=True,
            timeout=300,
            env={**os.environ, "PLAYWRIGHT_BROWSERS_PATH": PLAYWRIGHT_BROWSERS_DIR},
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except Exception as e:
        return {
            "returncode": 1,
            "stdout": "",
            "stderr": str(e),
        }


_playwright_status = installeer_playwright()

if _playwright_status["returncode"] != 0:
    st.error("Failed to install browsers")
    st.code(_playwright_status["stderr"] or _playwright_status["stdout"])
    st.stop()

# ─── Pagina-configuratie ───────────────────────────────────────────────────────
st.set_page_config(
    page_title="Striive Matcher",
    page_icon="⚡",
    layout="wide",
)

# ─── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'IBM Plex Sans', sans-serif;
}

.stApp {
    background-color: #0f1117;
    color: #e0e0e0;
}

section[data-testid="stSidebar"] {
    background-color: #161b22;
    border-right: 1px solid #2d333b;
}

h1, h2, h3 {
    font-family: 'IBM Plex Mono', monospace !important;
    letter-spacing: -0.5px;
}

.stButton > button {
    background-color: #238636;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    font-family: 'IBM Plex Mono', monospace;
    font-weight: 600;
    letter-spacing: 0.5px;
    padding: 0.6rem 1.4rem;
    transition: background-color 0.2s ease;
}
.stButton > button:hover {
    background-color: #2ea043;
}

div[data-testid="metric-container"] {
    background-color: #161b22;
    border: 1px solid #2d333b;
    border-radius: 8px;
    padding: 1rem 1.2rem;
}

.stDataFrame {
    border: 1px solid #2d333b;
    border-radius: 8px;
}

.log-box {
    background-color: #0d1117;
    border: 1px solid #2d333b;
    border-radius: 8px;
    padding: 1rem;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    color: #8b949e;
    height: 260px;
    overflow-y: auto;
    white-space: pre-wrap;
}

.badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    font-family: 'IBM Plex Mono', monospace;
}
.badge-green  { background-color: #1a4731; color: #3fb950; }
.badge-yellow { background-color: #3d2f00; color: #d29922; }
.badge-red    { background-color: #3d1a1a; color: #f85149; }

.stSlider label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 13px;
    color: #8b949e;
}

.stDownloadButton > button {
    background-color: #1f6feb;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    font-family: 'IBM Plex Mono', monospace;
    font-weight: 600;
}
.stDownloadButton > button:hover {
    background-color: #388bfd;
}

hr { border-color: #2d333b; }
</style>
""", unsafe_allow_html=True)

# ─── Hulpfuncties ─────────────────────────────────────────────────────────────

def normaliseer_url(url: str) -> str:
    """Maakt URL-vergelijking robuuster door trailing slash en spaties te verwijderen."""
    return (url or "").strip().rstrip("/")


def extraheer_uurtarief(tekst: str) -> str:
    patronen = [
        r'[Uu]urtarief[:\s]*[€]?\s*(\d+[\.,]?\d*)',
        r'[Tt]arief[:\s]*[€]?\s*(\d+[\.,]?\d*)',
        r'[€]\s*(\d+[\.,]?\d*)\s*per uur',
        r'(\d+[\.,]?\d*)\s*[€]?\s*per uur',
        r'[Hh]ourly rate[:\s]*[€$]?\s*(\d+[\.,]?\d*)',
        r'[Rr]ate[:\s]*[€$]?\s*(\d+[\.,]?\d*)',
    ]
    for patroon in patronen:
        match = re.search(patroon, tekst)
        if match:
            return f"€{match.group(1)}/uur"
    return "-"


def extraheer_startdatum(tekst: str) -> str:
    patronen = [
        r'[Ss]tartdatum[:\s]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
        r'[Ss]tart[:\s]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
        r'[Uu]iterlijk[:\s]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
        r'[Vv]oor\s+(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
        r'(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
    ]
    for patroon in patronen:
        match = re.search(patroon, tekst)
        if match:
            return match.group(1)
    return "-"


def extraheer_reageer_deadline(tekst: str) -> str:
    patronen = [
        r'[Rr]eageren kan t/m\s+(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
        r'[Rr]eageren kan t/m\s+(\d{1,2}\s+\w+\s+\d{4})',
        r'[Rr]eageren kan t/m\s+([^\n]+)',
    ]
    for patroon in patronen:
        match = re.search(patroon, tekst)
        if match:
            return match.group(1).strip()
    return "-"


def maak_excel(matches: List[dict]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Matches"

    headers = [
        "Opdracht #",
        "Kandidaat",
        "Score",
        "Uurtarief",
        "Startdatum",
        "Reageren t/m",
        "Link naar opdracht",
        "CV herschrijven",
    ]

    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True, color="FFFFFF", name="Arial")
        cell.fill = PatternFill("solid", start_color="2E4057")
        cell.alignment = Alignment(horizontal="center")

    breedtes = [12, 25, 10, 15, 18, 18, 50, 50]
    for i, breedte in enumerate(breedtes, 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = breedte

    for row_index, match in enumerate(matches, 2):
        waarden = [
            match["opdracht"],
            match["naam"],
            match["score"],
            match["uurtarief"],
            match["startdatum"],
            match["deadline"],
            match["url"],
            "https://chatgpt.com/g/g-692562722fd48191a45a59eef67f00f2-inthearena-cv-builder",
        ]

        for col, waarde in enumerate(waarden, 1):
            cell = ws.cell(row=row_index, column=col, value=waarde)
            cell.font = Font(name="Arial")
            cell.fill = PatternFill("solid", start_color="E8F5E9")

        link_cell = ws.cell(row=row_index, column=7, value=match["url"])
        link_cell.hyperlink = match["url"]
        link_cell.font = Font(name="Arial", color="0563C1", underline="single")

        cv_cell = ws.cell(row=row_index, column=8, value="Open CV Builder")
        cv_cell.hyperlink = "https://chatgpt.com/g/g-692562722fd48191a45a59eef67f00f2-inthearena-cv-builder"
        cv_cell.font = Font(name="Arial", color="0563C1", underline="single")

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def run_scraper(
    credentials: Dict[str, str],
    drempel: int,
    laatst_verwerkte_link: str,
    log_fn: Callable[[str], None],
    progress_fn: Callable[[int, int], None],
    result_fn: Callable[[List[dict]], None],
    batch_done_fn: Optional[Callable[[], None]] = None,
):
    """Voert de scrape uit in batches en werkt UI tussendoor bij."""
    from playwright.sync_api import sync_playwright

    COOLDOWN_SECONDEN = 3

    def log(msg: str):
        log_fn(msg)

    def chunks(lst, size):
        for i in range(0, len(lst), size):
            yield lst[i:i + size]

    def login_striive(page):
        log("🔐 Inloggen op Striive...")
        page.goto("https://login.striive.com/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

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
        for selector in email_selectors:
            try:
                element = page.locator(selector).first
                element.wait_for(state="visible", timeout=5000)
                email_veld = element
                log(f"  ✔ E-mailveld gevonden: {selector}")
                break
            except Exception:
                continue

        if email_veld is None:
            try:
                page.screenshot(path="/tmp/debug_login.png", full_page=True)
            except Exception:
                pass
            raise Exception("E-mailveld niet gevonden. Screenshot opgeslagen in /tmp/debug_login.png")

        email_veld.click()
        email_veld.fill(credentials["email"])

        wachtwoord_veld = page.locator('input[type="password"]').first
        wachtwoord_veld.wait_for(state="visible", timeout=10000)
        wachtwoord_veld.click()
        wachtwoord_veld.fill(credentials["wachtwoord"])

        login_selectors = [
            'button:has-text("Login")',
            'button:has-text("Inloggen")',
            'button[type="submit"]',
            'input[type="submit"]',
        ]

        for selector in login_selectors:
            try:
                knop = page.locator(selector).first
                knop.wait_for(state="visible", timeout=4000)
                knop.click()
                log(f"  Login-knop geklikt ({selector}).")
                break
            except Exception:
                continue
        else:
            wachtwoord_veld.press("Enter")
            log("  Login-knop niet gevonden, Enter gebruikt als fallback.")

        try:
            page.wait_for_selector('text=Overzicht', timeout=30000)
        except Exception:
            page.wait_for_url("**/dashboard**", timeout=30000)

        log("✅ Ingelogd!")

    def ga_naar_opdrachten(page):
        try:
            page.click('a:has-text("Opdrachten")', timeout=10000)
        except Exception:
            page.goto("https://supplier.striive.com/job-requests", wait_until="domcontentloaded", timeout=60000)

        page.wait_for_selector('[data-testid="jobRequestListItem"]', timeout=30000)
        page.wait_for_timeout(2000)
        log("✅ Opdrachtenpagina geladen.")

    def verzamel_opdracht_urls(page, stop_bij_link: Optional[str] = None) -> List[str]:
        """
        Verzamelt opdracht-URLs van nieuw naar oud.
        Als stop_bij_link is opgegeven, worden alleen URLs boven die link meegenomen.
        Zodra die link gevonden is, stopt de lijstopbouw.
        """
        stop_bij_link_norm = normaliseer_url(stop_bij_link)
        gebruik_stop_link = bool(stop_bij_link_norm)

        if gebruik_stop_link:
            log("🔍 Opdracht-URLs verzamelen tot aan laatst verwerkte link...")
            log(f"⛔ Stop-link ingesteld: {stop_bij_link_norm}")
        else:
            log("🔍 Alle opdracht-URLs verzamelen via scrollen...")

        alle_urls = []
        gevonden_set = set()
        stop_link_gevonden = False

        scroll_stap = 150
        scroll_pos = 0
        geen_nieuw = 0
        max_geen_nieuw = 8

        while geen_nieuw < max_geen_nieuw and not stop_link_gevonden:
            items = page.locator('[data-testid="jobRequestListItem"]').all()
            aantal_voor = len(gevonden_set)

            for item in items:
                try:
                    href = item.get_attribute('href')
                    if not href:
                        href = item.locator('a').first.get_attribute('href')

                    if not href:
                        continue

                    volledige_href = (
                        f"https://supplier.striive.com{href}"
                        if href.startswith("/")
                        else href
                    )
                    volledige_href_norm = normaliseer_url(volledige_href)

                    if volledige_href_norm == stop_bij_link_norm and gebruik_stop_link:
                        stop_link_gevonden = True
                        log("🛑 Laatst verwerkte link bereikt. Oudere opdrachten worden overgeslagen.")
                        break

                    if volledige_href_norm not in gevonden_set:
                        gevonden_set.add(volledige_href_norm)
                        alle_urls.append(volledige_href_norm)

                except Exception:
                    continue

            if stop_link_gevonden:
                break

            scroll_pos += scroll_stap

            try:
                res = page.evaluate(f"""
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
                        window.scrollTo(0, {scroll_pos});
                        return {{
                            scrollTop: window.scrollY,
                            scrollHeight: document.body.scrollHeight,
                            clientHeight: window.innerHeight
                        }};
                    }}
                """)
            except Exception:
                res = {"scrollTop": 0, "scrollHeight": 0, "clientHeight": 0}

            page.wait_for_timeout(1000)

            if len(gevonden_set) > aantal_voor:
                geen_nieuw = 0
            else:
                geen_nieuw += 1

            max_scroll = res["scrollHeight"] - res["clientHeight"]
            if max_scroll > 0 and res["scrollTop"] >= max_scroll - 10:
                log(f"📋 Einde van lijst bereikt. Totaal verzameld: {len(alle_urls)} opdrachten.")
                break

        if gebruik_stop_link and not stop_link_gevonden:
            log("⚠️ Stop-link niet gevonden in de huidige lijst. Alle gevonden opdrachten worden verwerkt.")

        log(f"📋 Totaal {len(alle_urls)} opdrachten geselecteerd voor verwerking.")
        return alle_urls

    def maak_streamlit_sessie(browser):
        """
        Open een nieuwe Streamlit-tab, log in en klik de juiste tab.
        Wacht langer zodat de app volledig opstaat na een koude start.
        """
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(
            "https://inthearenabv-cv-tool.streamlit.app/",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        page.wait_for_timeout(20000)

        frame = page.frame_locator("iframe").first

        try:
            wachtwoord_veld = frame.locator('input[type="password"]').first
            if wachtwoord_veld.is_visible(timeout=5000):
                wachtwoord_veld.fill(credentials["streamlit_pw"])
                frame.locator('button:has-text("Log in")').first.click()
                page.wait_for_timeout(15000)
                log("  🔑 Streamlit ingelogd.")
        except Exception:
            pass

        try:
            tab = frame.locator('button:has-text("Test geschiktheid opdracht")').first
            if tab.is_visible(timeout=5000):
                tab.click()
                page.wait_for_timeout(3000)
                log("  🖱️ Tab geklikt.")
        except Exception:
            pass

        try:
            frame.locator("textarea").first.wait_for(state="visible", timeout=30000)
            log("  ✅ Streamlit-sessie klaar.")
        except Exception:
            log("  ⚠️ Textarea nog niet zichtbaar na sessie-aanmaak, doorgaan...")

        return page

    def analyseer_in_streamlit(streamlit_page, browser, tekst, max_retries=2):
        """
        Hergebruikt een bestaande Streamlit-pagina.
        Bij fout: sluit de huidige pagina en maak een nieuwe sessie aan.
        Geeft (resultaten, streamlit_page) terug.
        """
        huidige_pagina = streamlit_page

        for poging in range(1, max_retries + 1):
            frame = huidige_pagina.frame_locator("iframe").first

            try:
                textarea = frame.locator("textarea").first
                textarea.wait_for(state="visible", timeout=30000)
                textarea.click(timeout=10000)
                textarea.fill("")
                textarea.fill(tekst)
                log(f"  ✍️ Tekst ingevuld (poging {poging}).")

                huidige_pagina.wait_for_timeout(2000)
                frame.locator('button:has-text("Analyseer geschiktheid")').first.click()
                log("  ⏳ Analyse gestart...")

                frame.locator("text=Resultaten").first.wait_for(timeout=90000)
                huidige_pagina.wait_for_timeout(5000)

                resultaten = []
                aantal_expanders = frame.locator('[data-testid="stExpander"]').count()

                for i in range(aantal_expanders):
                    try:
                        blok = frame.locator('[data-testid="stExpander"]').nth(i)

                        try:
                            blok.locator('summary, [data-testid="stExpanderToggleIcon"], button').first.click(timeout=5000)
                            huidige_pagina.wait_for_timeout(1000)
                        except Exception:
                            pass

                        blok_tekst = blok.inner_text(timeout=15000)
                        score_match = re.search(r'(\d+)/100', blok_tekst)
                        if not score_match:
                            continue

                        score = int(score_match.group(1))
                        naam_match = re.search(r'[🟢🟡🔴]\s*(.*?)\s*—\s*\d+/100', blok_tekst)
                        naam = naam_match.group(1).strip() if naam_match else "onbekend"

                        resultaten.append((naam, score))
                        log(f"  👤 {naam} → {score}/100")

                    except Exception as e:
                        log(f"  ⚠️ Kandidaatblok fout: {e}")

                return resultaten, huidige_pagina

            except Exception as e:
                log(f"  ⚠️ Streamlit fout (poging {poging}/{max_retries}): {e}")

                if poging < max_retries:
                    log("  🔄 Kapotte sessie sluiten, nieuwe Streamlit-sessie aanmaken...")
                    try:
                        huidige_pagina.close()
                    except Exception:
                        pass

                    try:
                        huidige_pagina = maak_streamlit_sessie(browser)
                    except Exception as nieuwe_sessie_fout:
                        log(f"  ❌ Nieuwe sessie aanmaken mislukt: {nieuwe_sessie_fout}")
                        break

        log("  ❌ Analyse opgegeven na alle pogingen.")
        return [], huidige_pagina

    # ── Hoofd scraper loop ───────────────────────────────────────────────────
    alle_matches = []
    mislukte_urls = []
    batch_grootte = 5

    with sync_playwright() as p:
        alle_urls = []
        init_browser = None

        try:
            init_browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )

            init_page = init_browser.new_page(viewport={"width": 1280, "height": 800})
            init_page.on("crash", lambda: log("💥 Init-page crash gedetecteerd"))
            init_browser.on("disconnected", lambda: log("🔌 Init-browser disconnected"))

            login_striive(init_page)
            ga_naar_opdrachten(init_page)
            alle_urls = verzamel_opdracht_urls(init_page, stop_bij_link=laatst_verwerkte_link)

        finally:
            try:
                if init_browser:
                    init_browser.close()
            except Exception:
                pass

        if not alle_urls:
            log("⚠️ Geen nieuwe opdrachten gevonden om te verwerken.")
            return []

        totaal = len(alle_urls)
        verwerkt = 0

        for batch_nummer, batch_urls in enumerate(chunks(alle_urls, batch_grootte), start=1):
            batch_browser = None
            streamlit_page = None

            log(f"\n📦 Start batch {batch_nummer} ({len(batch_urls)} opdrachten)")

            try:
                batch_browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                    ],
                )

                batch_browser.on("disconnected", lambda: log(f"🔌 Batch-browser {batch_nummer} disconnected"))

                striive_page = batch_browser.new_page(viewport={"width": 1280, "height": 800})
                striive_page.on("crash", lambda: log(f"💥 Striive-page crash in batch {batch_nummer}"))

                login_striive(striive_page)

                log("  🌐 Streamlit-sessie openen voor batch...")
                streamlit_page = maak_streamlit_sessie(batch_browser)

                for url in batch_urls:
                    verwerkt += 1
                    progress_fn(verwerkt, totaal)
                    log(f"\n[{verwerkt}/{totaal}] {url}")

                    try:
                        striive_page.goto(url, wait_until="domcontentloaded", timeout=60000)
                        striive_page.wait_for_timeout(2000)

                        tekst = striive_page.locator("app-job-request-details").inner_text(timeout=15000)

                        uurtarief = extraheer_uurtarief(tekst)
                        startdatum = extraheer_startdatum(tekst)
                        deadline = extraheer_reageer_deadline(tekst)

                        log(f"  💶 {uurtarief} | 📅 {startdatum} | ⏰ {deadline}")

                        time.sleep(COOLDOWN_SECONDEN)

                        kandidaten, streamlit_page = analyseer_in_streamlit(
                            streamlit_page,
                            batch_browser,
                            tekst,
                        )

                        for naam, score in kandidaten:
                            if score > drempel:
                                alle_matches.append({
                                    "opdracht": f"Opdracht {verwerkt}",
                                    "naam": naam,
                                    "score": score,
                                    "uurtarief": uurtarief,
                                    "startdatum": startdatum,
                                    "deadline": deadline,
                                    "url": url,
                                })
                                log(f"  ✅ Match! {naam} ({score}/100) boven drempel {drempel}.")
                                result_fn(alle_matches)

                    except Exception as e:
                        log(f"  ⚠️ Opdracht overgeslagen door fout: {e}")
                        mislukte_urls.append(url)
                        continue

            except Exception as e:
                log(f"❌ Batch {batch_nummer} gecrasht: {e}")
                for url in batch_urls:
                    if url not in mislukte_urls:
                        mislukte_urls.append(url)

            finally:
                try:
                    if streamlit_page:
                        streamlit_page.close()
                        log("  📕 Streamlit-sessie gesloten.")
                except Exception:
                    pass

                try:
                    if batch_browser:
                        batch_browser.close()
                except Exception:
                    pass

                log(f"📦 Batch {batch_nummer} afgesloten.")

                if batch_done_fn:
                    batch_done_fn()

    if mislukte_urls:
        log(f"\n⚠️ {len(mislukte_urls)} opdrachten mislukt of overgeslagen.")

    log(f"\n🏁 Klaar! {len(alle_matches)} matches gevonden.")
    return alle_matches


# ─── Session State initialisatie ──────────────────────────────────────────────
defaults = {
    "matches": [],
    "logs": [],
    "bezig": False,
    "klaar": False,
    "voortgang": (0, 0),
}

for key, default in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ─── UI ───────────────────────────────────────────────────────────────────────

col_logo, col_titel = st.columns([1, 8])
with col_logo:
    st.markdown("<div style='font-size:48px;padding-top:8px'>⚡</div>", unsafe_allow_html=True)
with col_titel:
    st.markdown("""
        <h1 style='margin:0;padding-top:12px;color:#e6edf3'>Striive Matcher</h1>
        <p style='color:#8b949e;margin:0;font-size:14px'>
            Automatisch opdrachten ophalen, analyseren en de beste kandidaten vinden.
        </p>
    """, unsafe_allow_html=True)

st.markdown("---")

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🔐 Inloggegevens")
    email = st.text_input("Striive e-mailadres", value="info@inthearena.nl")
    ww = st.text_input("Striive wachtwoord", type="password", value="InTheArena2@22")

    st.markdown("---")
    st.markdown("### 🤖 CV-tool")
    streamlit_pw = st.text_input("Streamlit wachtwoord", type="password", value="InTheArenaBV")

    st.markdown("---")
    st.markdown("### 🧷 Laatst verwerkte opdracht")
    laatst_verwerkte_link = st.text_input(
        "Link van de meest recent behandelde opdracht",
        value="",
        placeholder="https://supplier.striive.com/job-requests/...",
        help=(
            "Plak hier de link van de laatst verwerkte opdracht. "
            "Alleen opdrachten die boven deze link staan worden meegenomen. "
            "Laat leeg om alles te scannen."
        ),
    )

    st.markdown("---")
    st.markdown("### ⚙️ Instellingen")
    drempel = st.slider(
        "Minimale score",
        min_value=50,
        max_value=95,
        value=80,
        step=5,
        help="Alleen kandidaten boven deze score worden opgenomen.",
    )

    st.markdown("---")
    if isinstance(_playwright_status, dict) and _playwright_status.get("returncode") == 0:
        st.success("✅ Playwright Chromium klaar.", icon="✅")
    else:
        st.error("❌ Playwright-installatie mislukt.")
        if isinstance(_playwright_status, dict):
            st.code(_playwright_status.get("stderr") or _playwright_status.get("stdout") or "Onbekende fout")
        else:
            st.code(str(_playwright_status))

    st.caption("v1.3 · In The Arena BV")

# ─── Hoofd kolommen ───────────────────────────────────────────────────────────
col_links, col_rechts = st.columns([3, 2], gap="large")

with col_links:
    st.markdown("### 📊 Resultaten")
    metrics_placeholder = st.empty()
    resultaat_placeholder = st.empty()

with col_rechts:
    st.markdown("### 📋 Live log")
    log_placeholder = st.empty()

st.markdown("---")
col_btn, col_status = st.columns([2, 5])

with col_btn:
    start_knop = st.button(
        "🚀  Start analyse",
        disabled=st.session_state.bezig,
        use_container_width=True,
    )

with col_status:
    progress_placeholder = st.empty()


def render_resultaten():
    import pandas as pd

    with metrics_placeholder.container():
        metric_1, metric_2, metric_3 = st.columns(3)
        verwerkt, totaal = st.session_state.voortgang
        metric_1.metric("Verwerkt", f"{verwerkt}/{totaal}" if totaal else "0/0")
        metric_2.metric("Matches", len(st.session_state.matches))
        metric_3.metric("Drempelwaarde", f"{drempel}/100")

    resultaat_placeholder.empty()

    with resultaat_placeholder.container():
        if st.session_state.matches:
            df = pd.DataFrame(st.session_state.matches)
            df_weergave = df[["opdracht", "naam", "score", "uurtarief", "startdatum", "deadline"]].copy()
            df_weergave.columns = ["Opdracht", "Kandidaat", "Score", "Uurtarief", "Startdatum", "Reageren t/m"]
            df_weergave["CV Herschrijven"] = (
                "https://chatgpt.com/g/g-692562722fd48191a45a59eef67f00f2-inthearena-cv-builder"
            )

            st.dataframe(
                df_weergave,
                column_config={
                    "CV Herschrijven": st.column_config.LinkColumn(
                        "CV Herschrijven",
                        display_text="✏️ Open CV Builder",
                    )
                },
                use_container_width=True,
                hide_index=True,
            )

            if not st.session_state.bezig:
                excel_bytes = maak_excel(st.session_state.matches)
                st.download_button(
                    label="⬇️  Download als Excel",
                    data=excel_bytes,
                    file_name="striive_matches.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="download_excel_final",
                )

        elif st.session_state.klaar:
            st.info("Geen matches gevonden boven de ingestelde drempel.")
        else:
            st.markdown(
                "<p style='color:#8b949e;font-size:14px'>Nog geen resultaten. Start de analyse via de knop hieronder.</p>",
                unsafe_allow_html=True,
            )


def render_log():
    log_tekst = "\n".join(st.session_state.logs[-60:])
    log_placeholder.markdown(
        f"<div class='log-box'>{log_tekst}</div>",
        unsafe_allow_html=True,
    )


def render_progress():
    verwerkt, totaal = st.session_state.voortgang
    if st.session_state.bezig:
        if totaal:
            progress_placeholder.progress(verwerkt / totaal, text=f"Verwerken {verwerkt} van {totaal} opdrachten...")
        else:
            progress_placeholder.info("Bezig met opstarten...")
    else:
        progress_placeholder.empty()


render_resultaten()
render_log()
render_progress()

# ─── Scraper starten ──────────────────────────────────────────────────────────
if start_knop:
    if not email or not ww:
        st.error("Vul eerst je Striive-inloggegevens in.")
    else:
        st.session_state.bezig = True
        st.session_state.klaar = False
        st.session_state.matches = []
        st.session_state.logs = []
        st.session_state.voortgang = (0, 0)

        render_resultaten()
        render_log()
        render_progress()

        def log_fn(msg):
            st.session_state.logs.append(msg)
            render_log()

        def progress_fn(huidig, totaal):
            st.session_state.voortgang = (huidig, totaal)
            render_progress()
            render_resultaten()

        def result_fn(matches):
            st.session_state.matches = matches
            render_resultaten()

        def batch_done_fn():
            render_log()
            render_progress()
            render_resultaten()

        credentials = {
            "email": email,
            "wachtwoord": ww,
            "streamlit_pw": streamlit_pw,
        }

        try:
            matches = run_scraper(
                credentials=credentials,
                drempel=drempel,
                laatst_verwerkte_link=laatst_verwerkte_link,
                log_fn=log_fn,
                progress_fn=progress_fn,
                result_fn=result_fn,
                batch_done_fn=batch_done_fn,
            )
            st.session_state.matches = matches
            st.session_state.klaar = True
        except Exception as e:
            st.session_state.logs.append(f"\n❌ Fout: {e}")
            render_log()
        finally:
            st.session_state.bezig = False
            render_progress()
            render_resultaten()

        st.rerun()
