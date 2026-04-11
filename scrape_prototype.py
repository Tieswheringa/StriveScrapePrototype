import os
import re
import io
import subprocess
import sys
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

/* Donker industrieel thema */
.stApp {
    background-color: #0f1117;
    color: #e0e0e0;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background-color: #161b22;
    border-right: 1px solid #2d333b;
}

/* Headers */
h1, h2, h3 {
    font-family: 'IBM Plex Mono', monospace !important;
    letter-spacing: -0.5px;
}

/* Knoppen */
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

/* Metric kaartjes */
div[data-testid="metric-container"] {
    background-color: #161b22;
    border: 1px solid #2d333b;
    border-radius: 8px;
    padding: 1rem 1.2rem;
}

/* Tabel */
.stDataFrame {
    border: 1px solid #2d333b;
    border-radius: 8px;
}

/* Log-console */
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

/* Badge */
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

/* Drempelschuif label */
.stSlider label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 13px;
    color: #8b949e;
}

/* Download-knop */
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

/* Divider */
hr { border-color: #2d333b; }
</style>
""", unsafe_allow_html=True)


# ─── Hulpfuncties ─────────────────────────────────────────────────────────────

def extraheer_uurtarief(tekst: str) -> str:
    patronen = [
        r'[Uu]urtarief[:\s]*[€]?\s*(\d+[\.,]?\d*)',
        r'[Tt]arief[:\s]*[€]?\s*(\d+[\.,]?\d*)',
        r'[€]\s*(\d+[\.,]?\d*)\s*per uur',
        r'(\d+[\.,]?\d*)\s*[€]?\s*per uur',
        r'[Hh]ourly rate[:\s]*[€$]?\s*(\d+[\.,]?\d*)',
        r'[Rr]ate[:\s]*[€$]?\s*(\d+[\.,]?\d*)',
    ]
    for p in patronen:
        m = re.search(p, tekst)
        if m:
            return f"€{m.group(1)}/uur"
    return "-"


def extraheer_startdatum(tekst: str) -> str:
    patronen = [
        r'[Ss]tartdatum[:\s]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
        r'[Ss]tart[:\s]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
        r'[Uu]iterlijk[:\s]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
        r'[Vv]oor\s+(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
        r'(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
    ]
    for p in patronen:
        m = re.search(p, tekst)
        if m:
            return m.group(1)
    return "-"


def extraheer_reageer_deadline(tekst: str) -> str:
    patronen = [
        r'[Rr]eageren kan t/m\s+(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
        r'[Rr]eageren kan t/m\s+(\d{1,2}\s+\w+\s+\d{4})',
        r'[Rr]eageren kan t/m\s+([^\n]+)',
    ]
    for p in patronen:
        m = re.search(p, tekst)
        if m:
            return m.group(1).strip()
    return "-"


def maak_excel(matches: list) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Matches"

    headers = ["Opdracht #", "Kandidaat", "Score", "Uurtarief",
               "Startdatum", "Reageren t/m", "Link naar opdracht"]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = Font(bold=True, color="FFFFFF", name="Arial")
        cell.fill = PatternFill("solid", start_color="2E4057")
        cell.alignment = Alignment(horizontal="center")

    breedte = [12, 25, 10, 15, 18, 18, 50]
    for i, b in enumerate(breedte, 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = b

    for r, m in enumerate(matches, 2):
        for col, val in enumerate(
            [m["opdracht"], m["naam"], m["score"],
             m["uurtarief"], m["startdatum"], m["deadline"], m["url"]], 1
        ):
            cell = ws.cell(row=r, column=col, value=val)
            cell.font = Font(name="Arial")
            cell.fill = PatternFill("solid", start_color="E8F5E9")

        link_cell = ws.cell(row=r, column=7, value=m["url"])
        link_cell.hyperlink = m["url"]
        link_cell.font = Font(name="Arial", color="0563C1", underline="single")

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def run_scraper(credentials: dict, drempel: int, log_fn, progress_fn, result_fn):
    """Voert de volledige scrape uit. Roept callbacks aan voor UI-updates."""
    from playwright.sync_api import sync_playwright

    def log(msg):
        log_fn(msg)

    with sync_playwright() as p:
        # --no-sandbox + --disable-dev-shm-usage zijn verplicht op Linux-servers
        # (Streamlit Cloud, Docker, etc.) anders crasht Chromium of laadt pagina niet
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ]
        )
        page = browser.new_page(viewport={"width": 1280, "height": 800})

        page.on("crash", lambda: log("💥 Page crash gedetecteerd"))
        page.on("close", lambda: log("📕 Page gesloten"))
        browser.on("disconnected", lambda: log("🔌 Browser disconnected"))

        # ── Inloggen ──────────────────────────────────────────────────────────
        log("🔐 Inloggen op Striive...")
        page.goto("https://login.striive.com/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

        # E-mailveld: probeer meerdere selectors
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
                el = page.locator(sel).first
                el.wait_for(state="visible", timeout=5000)
                email_veld = el
                log(f"  ✔ E-mailveld gevonden: {sel}")
                break
            except:
                continue

        if email_veld is None:
            page.screenshot(path="/tmp/debug_login.png", full_page=True)
            raise Exception("E-mailveld niet gevonden. Screenshot opgeslagen in /tmp/debug_login.png")

        email_veld.click()
        email_veld.fill(credentials["email"])

        # Wachtwoordveld
        ww_veld = page.locator('input[type="password"]').first
        ww_veld.wait_for(state="visible", timeout=10000)
        ww_veld.click()
        ww_veld.fill(credentials["wachtwoord"])

        # Login-knop
        login_selectors = [
            'button:has-text("Login")',
            'button:has-text("Inloggen")',
            'button[type="submit"]',
            'input[type="submit"]',
        ]
        for sel in login_selectors:
            try:
                knop = page.locator(sel).first
                knop.wait_for(state="visible", timeout=4000)
                knop.click()
                log(f"  Login-knop geklikt ({sel}).")
                break
            except:
                continue
        else:
            # Fallback: Enter indrukken
            ww_veld.press("Enter")
            log("  Login-knop niet gevonden, Enter gebruikt als fallback.")

        # Wacht op succesvolle login
        try:
            page.wait_for_selector('text=Overzicht', timeout=30000)
        except:
            # Probeer alternatief dashboard-element
            page.wait_for_url("**/dashboard**", timeout=30000)

        log("✅ Ingelogd!")

        # Navigeer naar Opdrachten
        try:
            page.click('a:has-text("Opdrachten")', timeout=10000)
        except:
            # Probeer via directe URL
            page.goto("https://supplier.striive.com/job-requests")

        page.wait_for_selector('[data-testid="jobRequestListItem"]', timeout=30000)
        page.wait_for_timeout(2000)
        log("✅ Opdrachtenpagina geladen.")

        # ── Verzamel URLs ──────────────────────────────────────────────────────
        log("🔍 Alle opdracht-URLs verzamelen via scrollen...")
        alle_urls = []
        gevonden_set = set()
        scroll_stap, scroll_pos = 150, 0
        geen_nieuw, max_geen_nieuw = 0, 8

        while geen_nieuw < max_geen_nieuw:
            items = page.locator('[data-testid="jobRequestListItem"]').all()
            voor = len(gevonden_set)
            for item in items:
                try:
                    href = item.get_attribute('href') or item.locator('a').first.get_attribute('href')
                    if href and href not in gevonden_set:
                        gevonden_set.add(href)
                        if href.startswith('/'):
                            href = 'https://supplier.striive.com' + href
                        alle_urls.append(href)
                except:
                    pass

            scroll_pos += scroll_stap
            res = page.evaluate(f"""
                () => {{
                    const s = document.querySelector('div.p-scroller');
                    if (s) {{
                        s.scrollTop = {scroll_pos};
                        return {{scrollTop: s.scrollTop, scrollHeight: s.scrollHeight, clientHeight: s.clientHeight}};
                    }}
                    return {{scrollTop:0, scrollHeight:0, clientHeight:0}};
                }}
            """)
            page.wait_for_timeout(1000)

            geen_nieuw = 0 if len(gevonden_set) > voor else geen_nieuw + 1

            max_scroll = res['scrollHeight'] - res['clientHeight']
            if max_scroll > 0 and res['scrollTop'] >= max_scroll - 10:
                log(f"📋 Einde van lijst bereikt. Totaal: {len(alle_urls)} opdrachten.")
                break

        log(f"📋 Totaal {len(alle_urls)} opdrachten gevonden. Analyse starten...")

        # ── Streamlit-login (eenmalig) ────────────────────────────────────────
        streamlit_ingelogd = False

        alle_matches = []

        for i, url in enumerate(alle_urls[:1]):
            progress_fn(i + 1, len(alle_urls))
            log(f"\n[{i+1}/{len(alle_urls)}] {url}")

            try:
                page.goto(url)
                page.wait_for_timeout(2000)
                tekst = page.locator('app-job-request-details').inner_text(timeout=15000)
            except Exception as e:
                log(f"  ⚠️ Kon opdrachtdetails niet laden: {e}")
                continue

            uurtarief = extraheer_uurtarief(tekst)
            startdatum = extraheer_startdatum(tekst)
            deadline = extraheer_reageer_deadline(tekst)
            log(f"  💶 {uurtarief} | 📅 {startdatum} | ⏰ {deadline}")

            # ── Naar Streamlit CV-tool ─────────────────────────────────────────
            page.goto("https://inthearenabv-cv-tool.streamlit.app/")
            page.wait_for_timeout(8000)
            frame = page.frame_locator('iframe').first

            if not streamlit_ingelogd:
                try:
                    pw = frame.locator('input[type="password"]')
                    if pw.is_visible(timeout=5000):
                        pw.fill(credentials["streamlit_pw"])
                        frame.locator('button:has-text("Log in")').click()
                        page.wait_for_timeout(10000)
                        streamlit_ingelogd = True
                        log("  🔑 Streamlit ingelogd.")
                except:
                    streamlit_ingelogd = True

            try:
                frame.locator('button:has-text("Test geschiktheid opdracht")').click()
                page.wait_for_timeout(5000)
            except:
                pass

            try:
                ta = frame.locator('textarea').first
                ta.click(timeout=30000)
                ta.fill("")
                ta.fill(tekst)
            except Exception as e:
                log(f"  ⚠️ Kon tekst niet invullen: {e}")
                continue

            page.wait_for_timeout(3000)
            frame.locator('button:has-text("Analyseer geschiktheid")').click()
            log("  ⏳ Analyse gestart...")

            try:
                frame.locator('text=Resultaten').wait_for(timeout=120000)
                page.wait_for_timeout(5000)
            except Exception as e:
                log(f"  ⚠️ Resultaten niet gevonden: {e}")
                continue

            n_exp = frame.locator('[data-testid="stExpander"]').count()

            for j in range(n_exp):
                try:
                    blok = frame.locator('[data-testid="stExpander"]').nth(j)
                    try:
                        blok.locator('summary, [data-testid="stExpanderToggleIcon"], button').first.click(timeout=5000)
                        page.wait_for_timeout(1000)
                    except:
                        pass
                    blok_tekst = blok.inner_text(timeout=15000)
                except Exception as e:
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


# ─── Session State initialisatie ──────────────────────────────────────────────
for key, default in [
    ("matches", []),
    ("logs", []),
    ("bezig", False),
    ("klaar", False),
    ("voortgang", (0, 0)),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ─── UI ───────────────────────────────────────────────────────────────────────

# Header
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
    st.markdown("### ⚙️ Instellingen")
    drempel = st.slider("Minimale score", min_value=50, max_value=95, value=80, step=5,
                        help="Alleen kandidaten boven deze score worden opgenomen.")
    st.markdown("---")
    st.markdown("---")
    if _playwright_status.startswith("✅"):
        st.success(_playwright_status, icon="✅")
    else:
        st.error(_playwright_status)
    st.caption("v1.0 · In The Arena BV")

# ─── Hoofd kolommen ───────────────────────────────────────────────────────────
col_links, col_rechts = st.columns([3, 2], gap="large")

with col_links:
    st.markdown("### 📊 Resultaten")

    # Metrics
    m1, m2, m3 = st.columns(3)
    ged, tot = st.session_state.voortgang
    m1.metric("Verwerkt", f"{ged}/{tot}" if tot else "0/0")
    m2.metric("Matches", len(st.session_state.matches))
    m3.metric("Drempelwaarde", f"{drempel}/100")

    # Tabel
    if st.session_state.matches:
        import pandas as pd
        df = pd.DataFrame(st.session_state.matches)
        df_weergave = df[["opdracht", "naam", "score", "uurtarief", "startdatum", "deadline"]].copy()
        df_weergave.columns = ["Opdracht", "Kandidaat", "Score", "Uurtarief", "Startdatum", "Reageren t/m"]
        st.dataframe(
            df_weergave.style.background_gradient(subset=["Score"], cmap="Greens"),
            use_container_width=True,
            hide_index=True,
        )

        # Download knop
        excel_bytes = maak_excel(st.session_state.matches)
        st.download_button(
            label="⬇️  Download als Excel",
            data=excel_bytes,
            file_name="striive_matches.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    elif st.session_state.klaar:
        st.info("Geen matches gevonden boven de ingestelde drempel.")
    else:
        st.markdown(
            "<p style='color:#8b949e;font-size:14px'>Nog geen resultaten. Start de analyse via de knop hieronder.</p>",
            unsafe_allow_html=True
        )

with col_rechts:
    st.markdown("### 📋 Live log")
    log_placeholder = st.empty()

    def render_log():
        log_tekst = "\n".join(st.session_state.logs[-60:])
        log_placeholder.markdown(
            f"<div class='log-box'>{log_tekst}</div>",
            unsafe_allow_html=True
        )

    render_log()

# ─── Startknop ────────────────────────────────────────────────────────────────
st.markdown("---")
col_btn, col_status = st.columns([2, 5])

with col_btn:
    start_knop = st.button(
        "🚀  Start analyse",
        disabled=st.session_state.bezig,
        use_container_width=True,
    )

with col_status:
    if st.session_state.bezig:
        ged, tot = st.session_state.voortgang
        if tot:
            st.progress(ged / tot, text=f"Verwerken {ged} van {tot} opdrachten...")
        else:
            st.info("Bezig met opstarten...")

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

        def log_fn(msg):
            st.session_state.logs.append(msg)

        def progress_fn(huidig, totaal):
            st.session_state.voortgang = (huidig, totaal)

        def result_fn(matches):
            st.session_state.matches = matches

        credentials = {
            "email": email,
            "wachtwoord": ww,
            "streamlit_pw": streamlit_pw,
        }

        try:
            matches = run_scraper(credentials, drempel, log_fn, progress_fn, result_fn)
            st.session_state.matches = matches
            st.session_state.klaar = True
        except Exception as e:
            st.session_state.logs.append(f"\n❌ Fout: {e}")
        finally:
            st.session_state.bezig = False

        st.rerun()
