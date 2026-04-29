import logging
import re
import argparse
import platform
import time
import os
import sys
import multiprocessing
from typing import List, Optional
from dataclasses import dataclass, asdict, field
from datetime import datetime
from urllib.parse import urlparse, urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Page

# ─────────────────────────────────────────────
#  COULEURS & UI
# ─────────────────────────────────────────────

class Colors:
    RESET          = '\033[0m'
    BOLD           = '\033[1m'
    DIM            = '\033[2m'
    RED            = '\033[31m'
    GREEN          = '\033[32m'
    YELLOW         = '\033[33m'
    CYAN           = '\033[36m'
    BRIGHT_RED     = '\033[91m'
    BRIGHT_GREEN   = '\033[92m'
    BRIGHT_YELLOW  = '\033[93m'
    BRIGHT_BLUE    = '\033[94m'
    BRIGHT_MAGENTA = '\033[95m'
    BRIGHT_CYAN    = '\033[96m'
    WHITE          = '\033[97m'


def supports_color() -> bool:
    return hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()


def c(text: str, color: str) -> str:
    return f"{color}{text}{Colors.RESET}" if supports_color() else text


def print_c(text: str, color: str = Colors.WHITE) -> None:
    print(c(text, color))


def print_sep(char: str = "═", length: int = 80, color: str = Colors.CYAN) -> None:
    print_c(char * length, color)


def print_box(text: str, color: str = Colors.CYAN, width: int = 70) -> None:
    lines = text.split('\n')
    bw = max(width, max(len(l) for l in lines) + 4)
    print_c("╔" + "═" * (bw - 2) + "╗", color)
    for line in lines:
        print_c(f"║ {line}" + " " * (bw - len(line) - 3) + "║", color)
    print_c("╚" + "═" * (bw - 2) + "╝", color)


STATUS_ICONS = {
    "success":  ("[OK]     ", Colors.BRIGHT_GREEN),
    "error":    ("[ERR]    ", Colors.BRIGHT_RED),
    "warning":  ("[WARN]   ", Colors.BRIGHT_YELLOW),
    "info":     ("[INFO]   ", Colors.BRIGHT_BLUE),
    "search":   ("[SEARCH] ", Colors.BRIGHT_MAGENTA),
    "email":    ("[EMAIL]  ", Colors.BRIGHT_CYAN),
    "save":     ("[SAVE]   ", Colors.GREEN),
    "skip":     ("[SKIP]   ", Colors.DIM),
    "timeout":  ("[TIMEOUT]", Colors.YELLOW),
    "maps":     ("[MAPS]   ", Colors.BRIGHT_CYAN),
    "rocket":   ("[START]  ", Colors.BRIGHT_MAGENTA),
    "bulk":     ("[BULK]   ", Colors.BRIGHT_YELLOW),
}


def print_status(message: str, kind: str = "info") -> None:
    icon, color = STATUS_ICONS.get(kind, ("•", Colors.WHITE))
    print_c(f"{icon} {message}", color)


def print_header() -> None:
    os.system('cls' if os.name == 'nt' else 'clear')
    banner = r"""
 __  __  _   _   ____   __  __  _   _  ___  _     
|  \/  |/ | | | |  _ \ |  \/  || | | ||_ _|| |    
| |\/| || | | | | |_) || |\/| || |_| | | | | |    
| |  | || |_| | |  _ < | |  | ||  _  | | | | |___ 
|_|  |_|\___/  |_| \_\|_|  |_||_| |_||___||_____|
    Maps + Email Harvester  ·  V2.2  ·  By RDSV01
"""
    print_c(banner, Colors.BRIGHT_CYAN)
    print_c("  Google Maps scraper  ->  Website email harvester".center(55), Colors.BRIGHT_YELLOW)
    print()


def print_bulk_header(keyword: str, index: int, total: int) -> None:
    print()
    print_sep("═", 80, Colors.BRIGHT_YELLOW)
    print_c(f"  MOT-CLÉ [{index}/{total}] : {keyword}".center(80), Colors.BRIGHT_YELLOW + Colors.BOLD)
    print_sep("═", 80, Colors.BRIGHT_YELLOW)
    print()


# ─────────────────────────────────────────────
#  MODÈLE DE DONNÉES
# ─────────────────────────────────────────────

@dataclass
class Place:
    name:             str            = ""
    address:          str            = ""
    website:          str            = ""
    phone_number:     str            = ""
    reviews_count:    Optional[int]  = None
    reviews_average:  Optional[float]= None
    store_shopping:   str            = "No"
    in_store_pickup:  str            = "No"
    store_delivery:   str            = "No"
    place_type:       str            = ""
    opens_at:         str            = ""
    introduction:     str            = ""
    emails:           str            = ""   # emails séparés par ";"
    search_keyword:   str            = ""   # mot-clé source du résultat


# ─────────────────────────────────────────────
#  GOOGLE MAPS SCRAPER
# ─────────────────────────────────────────────

def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
    )


def extract_text(page: Page, xpath: str) -> str:
    try:
        loc = page.locator(xpath)
        if loc.count() > 0:
            return loc.first.inner_text()
    except Exception as e:
        logging.warning(f"Failed to extract text for xpath {xpath}: {e}")
    return ""


def extract_place(page: Page) -> Place:
    name_xpath          = '//div[@class="TIHn2 "]//h1[@class="DUwDvf lfPIob"]'
    address_xpath       = '//button[@data-item-id="address"]//div[contains(@class, "fontBodyMedium")]'
    website_xpath       = '//a[@data-item-id="authority"]//div[contains(@class, "fontBodyMedium")]'
    phone_number_xpath  = '//button[contains(@data-item-id, "phone:tel:")]//div[contains(@class, "fontBodyMedium")]'
    reviews_count_xpath = '//div[@class="TIHn2 "]//div[@class="fontBodyMedium dmRWX"]//div//span//span//span[@aria-label]'
    reviews_avg_xpath   = '//div[@class="F7nice"]//span[@aria-hidden="true"]'
    info1               = '//div[@class="LTs0Rc"][1]'
    info2               = '//div[@class="LTs0Rc"][2]'
    info3               = '//div[@class="LTs0Rc"][3]'
    opens_at_xpath      = '//button[contains(@data-item-id, "oh")]//div[contains(@class, "fontBodyMedium")]'
    opens_at_xpath2     = '//div[@class="MkV9"]//span[@class="ZDu9vd"]//span[2]'
    place_type_xpath    = '//div[@class="LBgpqf"]//button[@class="DkEaL "]'
    intro_xpath         = '//div[@class="WeS02d fontBodyMedium"]//div[@class="PYvSYb "]'

    place = Place()
    place.name         = extract_text(page, name_xpath)
    place.address      = extract_text(page, address_xpath)
    place.website      = extract_text(page, website_xpath)
    place.phone_number = extract_text(page, phone_number_xpath)
    place.place_type   = extract_text(page, place_type_xpath)
    place.introduction = extract_text(page, intro_xpath) or "None Found"

    # Reviews Count
    raw = extract_text(page, reviews_count_xpath)
    if raw:
        try:
            place.reviews_count = int(raw.replace('\xa0','').replace('(','').replace(')','').replace(',',''))
        except Exception:
            pass

    # Reviews Average
    raw = extract_text(page, reviews_avg_xpath)
    if raw:
        try:
            place.reviews_average = float(raw.replace(' ','').replace(',','.'))
        except Exception:
            pass

    # Store info
    for info_xpath in [info1, info2, info3]:
        raw = extract_text(page, info_xpath)
        if raw:
            parts = raw.split('·')
            if len(parts) > 1:
                check = parts[1].replace("\n","").lower()
                if 'shop'     in check: place.store_shopping  = "Yes"
                if 'pickup'   in check: place.in_store_pickup  = "Yes"
                if 'delivery' in check: place.store_delivery   = "Yes"

    # Opens At
    raw = extract_text(page, opens_at_xpath)
    if raw:
        parts = raw.split('⋅')
        place.opens_at = (parts[1] if len(parts) > 1 else parts[0]).replace("\u202f","")
    else:
        raw = extract_text(page, opens_at_xpath2)
        if raw:
            parts = raw.split('⋅')
            place.opens_at = (parts[1] if len(parts) > 1 else parts[0]).replace("\u202f","")

    return place


def find_chrome_path() -> Optional[str]:
    """Cherche Chrome dans les emplacements Windows courants. Retourne None si introuvable."""
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def scrape_maps(search_for: str, total: int, keyword: str = "") -> List[Place]:
    """Scrape Google Maps et retourne la liste des fiches."""
    setup_logging()
    places: List[Place] = []

    with sync_playwright() as p:
        launch_kwargs = {"headless": False}

        if platform.system() == "Windows":
            chrome_path = find_chrome_path()
            if chrome_path:
                print_status(f"Chrome trouvé : {chrome_path}", "info")
                launch_kwargs["executable_path"] = chrome_path
            else:
                print_status("Chrome introuvable — utilisation du Chromium intégré à Playwright.", "warning")
                print_status("Si ce n'est pas installé : playwright install chromium", "info")

        browser = p.chromium.launch(**launch_kwargs)

        page = browser.new_page()
        try:
            page.goto("https://www.google.com/maps", timeout=60000)
            page.wait_for_timeout(2000)

            # ── Gestion de la page de consentement cookies Google ──────────
            consent_selectors = [
                'button[aria-label="Tout accepter"]',
                'button[aria-label="Accept all"]',
                'button[aria-label="Accepter tout"]',
                'form[action*="consent"] button',
                '#L2AGLb',
            ]
            for sel in consent_selectors:
                try:
                    btn = page.locator(sel).first
                    if btn.is_visible(timeout=2000):
                        print_status("Page de consentement détectée — acceptation automatique.", "info")
                        btn.click()
                        page.wait_for_timeout(2000)
                        break
                except Exception:
                    pass

            # ── Navigation directe avec la recherche dans l'URL ─────────
            from urllib.parse import quote as _quote
            search_url = f"https://www.google.com/maps/search/{_quote(search_for)}"
            print_status(f"Navigation : {search_url}", "info")
            page.goto(search_url, timeout=60000)
            page.wait_for_timeout(2000)

            # Second consentement éventuel après redirection
            for sel in consent_selectors:
                try:
                    btn = page.locator(sel).first
                    if btn.is_visible(timeout=1500):
                        btn.click()
                        page.wait_for_timeout(2000)
                        page.goto(search_url, timeout=60000)
                        page.wait_for_timeout(2000)
                        break
                except Exception:
                    pass

            page.wait_for_selector(
                '//a[contains(@href, "https://www.google.com/maps/place")]',
                timeout=30000
            )

            # ── Localise le panneau de résultats scrollable ──────────────
            PANEL_SELECTORS = [
                'div[role="feed"]',
                'div.m6QErb[aria-label]',
                'div.m6QErb.DxyBCb',
                'div.m6QErb',
            ]
            panel = None
            for sel in PANEL_SELECTORS:
                loc = page.locator(sel).first
                try:
                    if loc.is_visible(timeout=3000):
                        panel = loc
                        print_status(f"Panneau de résultats trouvé : {sel}", "info")
                        break
                except Exception:
                    pass

            if panel is None:
                print_status("Panneau scrollable introuvable — fallback scroll page entière.", "warning")

            # ── Scroll infini jusqu'à `total` résultats ou fin de liste ──
            previously_counted = 0
            stall_count        = 0
            MAX_STALL          = 4

            while True:
                if panel:
                    panel.evaluate("el => el.scrollBy(0, 3000)")
                else:
                    page.mouse.wheel(0, 5000)

                page.wait_for_timeout(1800)

                found = page.locator(
                    '//a[contains(@href, "https://www.google.com/maps/place")]'
                ).count()
                print_status(f"Résultats Maps trouvés : {found}", "maps")

                end_of_list = page.locator(
                    "text=/Vous avez atteint la fin|You've reached the end|No more results/i"
                ).count() > 0
                if end_of_list:
                    print_status("Fin de liste Google Maps détectée.", "info")
                    break

                if found >= total:
                    break

                if found == previously_counted:
                    stall_count += 1
                    if stall_count >= MAX_STALL:
                        print_status(
                            f"Scroll bloqué ({stall_count}x sans nouveaux résultats) — arrêt.",
                            "warning"
                        )
                        break
                else:
                    stall_count = 0

                previously_counted = found

            listings = page.locator('//a[contains(@href, "https://www.google.com/maps/place")]').all()[:total]
            listings = [l.locator("xpath=..") for l in listings]
            print_status(f"{len(listings)} fiches à traiter", "info")
            print_sep("─", 60, Colors.CYAN)

            for idx, listing in enumerate(listings, 1):
                try:
                    listing.click()
                    page.wait_for_selector('//div[@class="TIHn2 "]//h1[@class="DUwDvf lfPIob"]', timeout=10000)
                    time.sleep(1.5)
                    place = extract_place(page)
                    if place.name:
                        place.search_keyword = keyword  # tag du mot-clé source
                        places.append(place)
                        print_status(f"[{idx}/{len(listings)}] {place.name}", "maps")
                    else:
                        print_status(f"[{idx}/{len(listings)}] Nom introuvable, ignoré.", "skip")
                except Exception as e:
                    print_status(f"[{idx}/{len(listings)}] Échec : {e}", "error")
        finally:
            browser.close()

    return places


# ─────────────────────────────────────────────
#  EMAIL SCRAPER
# ─────────────────────────────────────────────

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/91.0 Safari/537.36"
REQUEST_DELAY = 1

EXCLUDED_DOMAINS = {
    'google.com','bing.com','duckduckgo.com','yahoo.com','facebook.com',
    'twitter.com','instagram.com','linkedin.com','youtube.com','wikipedia.org',
    'pages-jaunes.fr','pagesjaunes.fr','yelp.com','tripadvisor.com',
    'booking.com','booking.fr','microsoft.com','fr.kompass.com',
    'pappers.fr','societe.com','sortlist.com','pointdecontact.net',
    'e-pro.fr','annuaire-mairie.fr','hellowork.com','118000.fr',
    'petitfute.com','thefork.fr','guide.michelin.com','restaurantguru.com',
    'tripadvisor.fr','tripadvisor.ch','ovh.com','test.fr',
}

EXCLUDED_EMAIL_DOMAINS = {
    'ovh.com','test.fr','example.com','exemple.fr','sample.com',
    'noreply.com','no-reply.com','donotreply.com','nospam.com',
}

VALID_EMAIL_EXTENSIONS = ('.fr','.com','.net','.org','.io','.co')


def is_site_excluded(url: str) -> bool:
    domain = urlparse(url).netloc.lower()
    return any(domain.endswith(ex) for ex in EXCLUDED_DOMAINS)


def is_email_excluded(email: str) -> bool:
    return email.split('@')[-1].lower() in EXCLUDED_EMAIL_DOMAINS


def extract_emails(text: str) -> List[str]:
    pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'
    raw = re.findall(pattern, text, re.IGNORECASE)
    result = set()
    for e in raw:
        e = re.split(r'[^a-zA-Z0-9.@_-]', e)[0].lower()
        if e.endswith(VALID_EMAIL_EXTENSIONS) and not is_email_excluded(e):
            result.add(e)
    return list(result)


def get_page_content(url: str) -> Optional[str]:
    try:
        r = requests.get(url, headers={'User-Agent': USER_AGENT}, timeout=10)
        r.raise_for_status()
        return r.text
    except Exception:
        return None


def find_contact_url(main_url: str) -> Optional[str]:
    content = get_page_content(main_url)
    if not content:
        return None
    soup = BeautifulSoup(content, 'html.parser')
    keywords = ['contact','nous-contacter','about','about-us','contact-us','contactez-nous']
    for link in soup.find_all('a', href=True):
        if any(kw in link['href'].lower() for kw in keywords):
            return urljoin(main_url, link['href'])
    return None


def _find_emails_in_website(url: str, check_contact: bool = True) -> List[str]:
    content = get_page_content(url)
    if not content:
        return []
    soup = BeautifulSoup(content, 'html.parser')
    emails = extract_emails(soup.get_text())
    for link in soup.select('a[href^="mailto:"]'):
        email = link['href'].replace('mailto:','').strip().lower()
        if email and not is_email_excluded(email):
            emails.append(email)
    emails = extract_emails(' '.join(emails))
    if not emails and check_contact:
        contact_url = find_contact_url(url)
        if contact_url and contact_url != url:
            return _find_emails_in_website(contact_url, check_contact=False)
    return list(set(emails))


def _worker(url: str):
    """Exécuté dans un sous-processus pour respecter le timeout."""
    return _find_emails_in_website(url)


def scrape_emails_from_url(url: str, timeout: int = 12) -> List[str]:
    """Wrapper avec timeout multiprocessing."""
    if not url:
        return []
    if not url.startswith('http'):
        url = 'https://' + url
    if is_site_excluded(url):
        return []
    with multiprocessing.Pool(processes=1) as pool:
        result = pool.apply_async(_worker, (url,))
        try:
            return result.get(timeout)
        except multiprocessing.TimeoutError:
            print_status(f"Timeout pour {url}", "timeout")
            return []
        except Exception as e:
            print_status(f"Erreur scraping email {url}: {e}", "error")
            return []


# ─────────────────────────────────────────────
#  PIPELINE PRINCIPAL
# ─────────────────────────────────────────────

def enrich_places_with_emails(places: List[Place], max_per_site: int = 1) -> List[Place]:
    """Pour chaque fiche, scrape les emails depuis le site web (max_per_site emails max)."""
    print()
    print_sep("═", 80, Colors.BRIGHT_MAGENTA)
    print_c("  ENRICHISSEMENT PAR EMAILS".center(80), Colors.BRIGHT_MAGENTA + Colors.BOLD)
    print_sep("═", 80, Colors.BRIGHT_MAGENTA)
    print()

    for idx, place in enumerate(places, 1):
        prefix = f"[{idx}/{len(places)}] {place.name}"
        if not place.website:
            print_status(f"{prefix} - pas de site web, ignore", "skip")
            continue

        print_status(f"{prefix} - {place.website}", "search")
        emails = scrape_emails_from_url(place.website)

        if emails:
            emails = emails[:max_per_site]
            place.emails = ";".join(emails)
            print_status(f"  -> {len(emails)} email(s) : {place.emails}", "email")
        else:
            print_status(f"  -> aucun email trouve", "warning")

        time.sleep(REQUEST_DELAY)

    return places


def save_to_csv(places: List[Place], output_path: str, append: bool = False) -> None:
    df = pd.DataFrame([asdict(p) for p in places])
    if df.empty:
        print_status("Aucune donnée à sauvegarder.", "warning")
        return
    for col in df.columns:
        if df[col].nunique() <= 1 and col != "search_keyword":
            df.drop(col, axis=1, inplace=True)
    mode   = "a" if append else "w"
    header = not (append and os.path.isfile(output_path))
    df.to_csv(output_path, index=False, mode=mode, header=header)
    print_status(f"{len(df)} lignes sauvegardées → {output_path}", "save")


def display_summary(
    places: List[Place],
    output_path: str,
    excluded_count: int = 0,
    keywords: Optional[List[str]] = None,
) -> None:
    total_with_email = sum(1 for p in places if p.emails)
    print()
    print_sep("═", 80, Colors.BRIGHT_GREEN)
    excluded_line = f"  Fiches exclues    : {excluded_count} (sans site ni email)\n" if excluded_count else ""
    kw_line = f"  Mots-clés         : {len(keywords)} ({', '.join(keywords)})\n" if keywords and len(keywords) > 1 else ""
    summary = (
        f"✅ TERMINÉ\n\n"
        f"{kw_line}"
        f"  Fiches scrappées  : {len(places)}\n"
        f"  Avec email(s)     : {total_with_email}\n"
        f"  Sans email        : {len(places) - total_with_email}\n"
        f"{excluded_line}"
        f"  Fichier de sortie : {output_path}\n"
        f"  Date              : {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
    )
    print_box(summary, Colors.BRIGHT_GREEN)
    print_sep("═", 80, Colors.BRIGHT_GREEN)


def parse_keywords(raw: str) -> List[str]:
    """Découpe une chaîne de mots-clés séparés par ',' ou ';' et nettoie les espaces."""
    parts = re.split(r'[,;]', raw)
    return [p.strip() for p in parts if p.strip()]


# ─────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────

def get_user_input_interactive():
    print_header()
    print_c("CONFIGURATION", Colors.BRIGHT_YELLOW)
    print_sep("─", 50, Colors.YELLOW)

    while True:
        raw_query = input(c(
            "Requetes Google Maps — Vous pouvez séparer plusieurs mots-clés par une virgule\n"
            "  ex: restaurants paris 15e, pizzerias lyon, sushi bordeaux\n> ",
            Colors.BRIGHT_CYAN
        )).strip()
        if raw_query:
            keywords = parse_keywords(raw_query)
            if keywords:
                break
        print_status("La requête ne peut pas être vide.", "error")

    while True:
        try:
            raw = input(c("Nombre de fiches à scraper PAR mot-clé (defaut: 10) : ", Colors.BRIGHT_CYAN)).strip()
            total = int(raw) if raw else 10
            if total > 0:
                break
            print_status("Doit être > 0.", "error")
        except ValueError:
            print_status("Nombre invalide.", "error")

    while True:
        raw = input(c("Fichier de sortie (defaut: result.csv) : ", Colors.BRIGHT_CYAN)).strip()
        output = raw if raw else "result.csv"
        break

    while True:
        try:
            raw = input(c("Emails max par site (defaut: 1) : ", Colors.BRIGHT_CYAN)).strip()
            max_per_site = int(raw) if raw else 1
            if max_per_site > 0:
                break
            print_status("Doit etre > 0.", "error")
        except ValueError:
            print_status("Nombre invalide.", "error")

    while True:
        raw = input(c("Exclure les fiches sans site web ET sans email ? (o/n, defaut: n) : ", Colors.BRIGHT_CYAN)).strip().lower()
        if raw in ('', 'o', 'n'):
            only_with_contact = (raw == 'o')
            break
        print_status("Repondre par 'o' ou 'n'.", "error")

    print()
    only_contact_label = "Oui" if only_with_contact else "Non"
    kw_display = "\n".join(f"    {i+1}. {kw}" for i, kw in enumerate(keywords))
    print_box(
        f"CONFIGURATION\n\n"
        f"  Mots-clés ({len(keywords)}) :\n{kw_display}\n"
        f"  Fiches / mot-clé  : {total}\n"
        f"  Emails/site       : {max_per_site}\n"
        f"  Sortie            : {output}\n"
        f"  Exclure sans contact : {only_contact_label}",
        Colors.BRIGHT_GREEN
    )
    input(c("\nAppuyez sur Entree pour demarrer...", Colors.BRIGHT_YELLOW))
    return keywords, total, output, max_per_site, only_with_contact


def run_pipeline_for_keyword(
    keyword: str,
    kw_index: int,
    kw_total: int,
    total: int,
    output_path: str,
    max_per_site: int,
    only_with_contact: bool,
    no_emails: bool,
    first_keyword: bool,
) -> List[Place]:
    """Exécute le pipeline complet (Maps + emails + filtre + CSV) pour un seul mot-clé."""

    print_bulk_header(keyword, kw_index, kw_total)

    # ── Étape 1 : Google Maps ──────────────────
    print_sep("═", 80, Colors.BRIGHT_CYAN)
    print_c("  SCRAPING GOOGLE MAPS".center(80), Colors.BRIGHT_CYAN + Colors.BOLD)
    print_sep("═", 80, Colors.BRIGHT_CYAN)
    print()

    places = scrape_maps(keyword, total, keyword=keyword)
    print_status(f"{len(places)} fiches recuperees depuis Google Maps.", "success")

    # ── Étape 2 : Emails ──────────────────────
    if not no_emails:
        places = enrich_places_with_emails(places, max_per_site=max_per_site)
    else:
        print_status("Scraping d'emails desactive (--no-emails).", "skip")

    # ── Étape 2.5 : Filtrage fiches sans contact ──────────────────────
    excluded_count = 0
    if only_with_contact:
        before = len(places)
        places = [p for p in places if p.website and p.emails]
        excluded_count = before - len(places)
        if excluded_count:
            print_status(
                f"{excluded_count} fiche(s) exclue(s) du CSV (pas de site web ni d'email).",
                "skip"
            )
        else:
            print_status("Aucune fiche exclue (toutes ont un site ou un email).", "info")

    # ── Étape 3 : Sauvegarde (append sauf toute première écriture) ────
    file_already_exists = os.path.isfile(output_path)
    append_mode = file_already_exists or not first_keyword
    save_to_csv(places, output_path, append=append_mode)

    return places


def main():
    parser = argparse.ArgumentParser(
        description="Scrape Google Maps + emails depuis les sites web des fiches. "
                    "Supporte plusieurs mots-clés séparés par une virgule."
    )
    parser.add_argument(
        "-s", "--search",
        type=str,
        help="Requête(s) de recherche Google Maps. "
             "Séparez plusieurs mots-clés par une virgule : "
             "\"restaurants paris 15e, pizzerias lyon\""
    )
    parser.add_argument("-t", "--total",             type=int,  default=10,         help="Nombre de fiches à scraper PAR mot-clé")
    parser.add_argument("-o", "--output",            type=str,  default="result.csv", help="Fichier CSV de sortie")
    parser.add_argument("--append",                  action="store_true",            help="Ajouter au CSV existant dès le premier mot-clé")
    parser.add_argument("--no-emails",               action="store_true",            help="Desactiver le scraping d'emails")
    parser.add_argument("--max-per-site",            type=int,  default=None,        help="Emails max par site (defaut: 1)")
    parser.add_argument("--only-with-contact",       action="store_true",
                        help="Exclure du CSV les fiches sans site web ni email")
    args = parser.parse_args()

    if args.search:
        print_header()
        keywords          = parse_keywords(args.search)
        total             = args.total
        output_path       = args.output
        max_per_site      = args.max_per_site if args.max_per_site is not None else 1
        only_with_contact = args.only_with_contact
        no_emails         = args.no_emails
        # En mode CLI, --append force l'ajout au fichier existant dès le départ
        first_is_append   = args.append
    else:
        keywords, total, output_path, max_per_site, only_with_contact = get_user_input_interactive()
        no_emails       = False
        first_is_append = False

    if not keywords:
        print_status("Aucun mot-clé valide fourni. Arrêt.", "error")
        sys.exit(1)

    if len(keywords) > 1:
        print_status(f"Mode BULK activé : {len(keywords)} mots-clés à traiter.", "bulk")
        for kw in keywords:
            print_status(f"  • {kw}", "bulk")
        print()

    # ── Boucle sur les mots-clés ──────────────────────────────────────
    all_places: List[Place] = []

    for idx, keyword in enumerate(keywords, 1):
        first_keyword = (idx == 1) and not first_is_append
        places = run_pipeline_for_keyword(
            keyword          = keyword,
            kw_index         = idx,
            kw_total         = len(keywords),
            total            = total,
            output_path      = output_path,
            max_per_site     = max_per_site,
            only_with_contact= only_with_contact,
            no_emails        = no_emails,
            first_keyword    = first_keyword,
        )
        all_places.extend(places)

    # ── Résumé global ──────────────────────────────────────────────────
    excluded_total = 0  # déjà filtrés à l'écriture par mot-clé
    display_summary(
        places      = all_places,
        output_path = output_path,
        excluded_count = excluded_total,
        keywords    = keywords,
    )


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()