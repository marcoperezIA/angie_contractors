"""
Scraper de empresas desde Angi.com (Florida - Miami area y todo el estado)
Recorre TODAS las ciudades de FL, extrae empresas con:
nombre, teléfono, ubicación, dirección, website, services, about.
Usa BeautifulSoup para parsear HTML rápido.
Guarda al CSV en tiempo real.
"""

import csv
import os
import re
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth


BASE_URL = "https://www.angi.com/companylist/us/fl/"
OUTPUT_FILE = "angie_companies_fl.csv"
FIELDNAMES = ["name", "phone", "location", "address", "website", "services", "about", "url"]

# Ciudades de Florida — ordenadas de mayor a menor población/importancia
TARGET_CITIES = [
    # =========================================================
    # 1. MIAMI METRO AREA — primero (más leads)
    # =========================================================
    "miami",                # ~450k hab — ciudad principal
    "miami-beach",          # ~90k hab
    "hialeah",              # ~220k hab
    "coral-gables",         # ~50k hab
    "miami-gardens",        # ~110k hab
    "homestead",            # ~75k hab
    "north-miami",          # ~62k hab
    "north-miami-beach",    # ~44k hab
    "opa-locka",
    "miami-lakes",
    "doral",
    "kendall",
    "westchester",
    "cutler-bay",
    "pinecrest",
    "south-miami",
    "miami-shores",
    "brickell",
    "wynwood",
    "little-havana",
    "coconut-grove",
    "overtown",
    "liberty-city",
    "little-haiti",
    "downtown-miami",

    # --- Miami-Dade (resto) ---
    "aventura",
    "sunny-isles-beach",
    "bal-harbour",
    "surfside",
    "bay-harbor-islands",
    "florida-city",
    "key-biscayne",
    "sweetwater",
    "medley",
    "virginia-gardens",

    # =========================================================
    # 2. BROWARD COUNTY (Fort Lauderdale area)
    # =========================================================
    "fort-lauderdale",      # ~180k hab
    "pembroke-pines",       # ~170k hab
    "hollywood",            # ~150k hab
    "miramar",              # ~130k hab
    "sunrise",              # ~95k hab
    "plantation",           # ~90k hab
    "coral-springs",        # ~130k hab
    "pompano-beach",        # ~110k hab
    "davie",                # ~105k hab
    "weston",               # ~70k hab
    "deerfield-beach",      # ~80k hab
    "margate",              # ~55k hab
    "coconut-creek",        # ~60k hab
    "tamarac",              # ~60k hab
    "lauderhill",
    "lauderdale-lakes",
    "north-lauderdale",
    "hallandale-beach",
    "dania-beach",
    "wilton-manors",
    "oakland-park",
    "lighthouse-point",
    "parkland",

    # =========================================================
    # 3. PALM BEACH COUNTY
    # =========================================================
    "west-palm-beach",      # ~115k hab
    "boca-raton",           # ~100k hab
    "boynton-beach",        # ~80k hab
    "delray-beach",         # ~65k hab
    "palm-beach-gardens",   # ~55k hab
    "wellington",           # ~65k hab
    "lake-worth",           # ~40k hab
    "riviera-beach",        # ~35k hab
    "jupiter",              # ~60k hab
    "palm-springs",
    "greenacres",
    "royal-palm-beach",
    "loxahatchee",
    "belle-glade",

    # =========================================================
    # 4. ORLANDO METRO AREA
    # =========================================================
    "orlando",              # ~310k hab
    "kissimmee",            # ~75k hab
    "sanford",              # ~60k hab
    "apopka",               # ~55k hab
    "altamonte-springs",    # ~44k hab
    "winter-park",          # ~30k hab
    "oviedo",               # ~38k hab
    "clermont",             # ~38k hab
    "lakeland",             # ~115k hab
    "winter-garden",        # ~45k hab
    "longwood",
    "casselberry",
    "maitland",
    "deltona",              # ~90k hab
    "daytona-beach",        # ~70k hab
    "port-orange",          # ~60k hab

    # =========================================================
    # 5. TAMPA BAY AREA
    # =========================================================
    "tampa",                # ~395k hab
    "st-petersburg",        # ~260k hab
    "clearwater",           # ~115k hab
    "brandon",              # ~115k hab
    "riverview",            # ~90k hab
    "palm-harbor",
    "new-port-richey",
    "spring-hill",
    "land-o-lakes",
    "lutz",
    "temple-terrace",
    "dunedin",
    "safety-harbor",
    "tarpon-springs",
    "largo",
    "pinellas-park",
    "st-pete-beach",
    "sarasota",             # ~55k hab
    "bradenton",            # ~55k hab
    "venice",
    "north-port",
    "cape-coral",           # ~190k hab
    "fort-myers",           # ~85k hab
    "naples",               # ~22k hab
    "bonita-springs",
    "estero",
    "lehigh-acres",

    # =========================================================
    # 6. JACKSONVILLE AREA (norte de FL)
    # =========================================================
    "jacksonville",         # ~950k hab — ciudad más grande de FL
    "jacksonville-beach",
    "neptune-beach",
    "atlantic-beach",
    "orange-park",
    "fleming-island",
    "palm-coast",           # ~90k hab
    "st-augustine",         # ~15k hab (histórica)
    "gainesville",          # ~135k hab
    "ocala",                # ~60k hab
    "tallahassee",          # ~195k hab (capital)
    "pensacola",            # ~55k hab
    "panama-city",          # ~36k hab
    "port-st-lucie",        # ~200k hab
    "fort-pierce",          # ~45k hab
    "stuart",
    "melbourne",            # ~80k hab
    "palm-bay",             # ~115k hab
    "titusville",           # ~45k hab
]


def init_csv():
    if not os.path.exists(OUTPUT_FILE) or os.path.getsize(OUTPUT_FILE) == 0:
        with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()


def append_to_csv(company):
    with open(OUTPUT_FILE, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=FIELDNAMES).writerow(company)


def get_saved_urls():
    saved = set()
    if os.path.exists(OUTPUT_FILE) and os.path.getsize(OUTPUT_FILE) > 0:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                saved.add(row.get("url", ""))
    return saved


def location_from_url(url):
    match = re.search(r"/us/fl/([^/]+)/", url)
    if match:
        return match.group(1).replace("-", " ").title()
    return ""


def collect_companies_from_city(page, city_slug, max_pages=10):
    """Entra a una ciudad y recorre sus páginas para sacar empresas (.htm)."""
    city_url = f"{BASE_URL}{city_slug}/"
    companies = []
    seen = set()

    for pg in range(1, max_pages + 1):
        url = f"{city_url}?page={pg}" if pg > 1 else city_url
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(1000)
        except Exception:
            break

        html = page.content()
        soup = BeautifulSoup(html, "html.parser")

        new_count = 0
        for a in soup.find_all("a", href=True):
            href = a["href"]
            name = a.get_text(strip=True)
            if ".htm" in href and "/companylist/us/fl/" in href and 2 < len(name) < 120:
                full_url = href if href.startswith("http") else f"https://www.angi.com{href}"
                if full_url not in seen:
                    seen.add(full_url)
                    companies.append({"name": name, "url": full_url})
                    new_count += 1

        if new_count == 0:
            break
        page.wait_for_timeout(500)

    return companies


def parse_detail_html(html, name, url):
    """Parsea el HTML de detalle con BeautifulSoup. Rápido."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    location = location_from_url(url)
    phone = ""
    address = ""
    website = ""
    services = ""
    about = ""

    # --- TELÉFONO: buscar link tel: ---
    tel_link = soup.find("a", href=re.compile(r"^tel:"))
    if tel_link:
        num = tel_link["href"].replace("tel:", "").strip()
        if len(num) >= 10:
            phone = num
    if not phone:
        m = re.search(r"\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}", text)
        if m:
            phone = m.group(0)

    # --- CONTACT INFORMATION (dirección + website) ---
    ci = text.find("Contact Information")
    if ci != -1:
        chunk = text[ci + 19:ci + 400]
        lines = [l.strip() for l in chunk.split("\n") if l.strip()]
        addr_lines = []
        for line in lines:
            if line.startswith("http") or line.startswith("www."):
                website = line
                continue
            if any(line.startswith(s) for s in ("Service", "About", "Business", "Review")):
                break
            if re.search(r"\d", line) or re.search(r",\s*[A-Z]{2}", line) or addr_lines:
                addr_lines.append(line)
                if re.search(r"\d{5}", line):
                    break
        address = ", ".join(addr_lines)

    # Website fallback: links externos
    if not website:
        for a in soup.find_all("a", href=re.compile(r"^https?://")):
            h = a["href"]
            skip = ("angi.com", "google", "facebook", "yelp", "bbb.org", "twitter", "instagram", "youtube")
            if not any(s in h for s in skip) and len(h) > 10:
                website = h
                break

    # --- SERVICES (sección "Services we offer") ---
    si = text.find("Services we offer")
    if si != -1:
        chunk = text[si + 17:si + 400]
        lines = [l.strip() for l in chunk.split("\n") if l.strip()]
        svc_list = []
        stop = re.compile(r"^(About|Business|Review|Photo|Request|More|Amenities|VIEW|Our recent|Meet|Before|Accepted|Free Estimates|Warranties|Emergency|Yes|No|CreditCard|Check)", re.I)
        for line in lines:
            if stop.match(line):
                break
            if 1 < len(line) < 80:
                svc_list.append(line)
        services = ", ".join(svc_list)

    # --- ABOUT US ---
    ai = text.find("About us")
    if ai != -1:
        chunk = text[ai + 8:ai + 1500]
        lines = [l.strip() for l in chunk.split("\n") if l.strip()]
        about_lines = []
        for line in lines:
            if line in ("Read less", "Read more") or any(line.startswith(s) for s in
                ("Business highlights", "Services we offer", "Photo", "Review", "Request")):
                break
            if len(line) > 5:
                about_lines.append(line)
        about = " ".join(about_lines)[:800]

    return {
        "name": name, "phone": phone, "location": location,
        "address": address, "website": website,
        "services": services, "about": about, "url": url,
    }


def scrape_company_detail(page, company):
    """Visita detalle: click phone, luego parsea HTML con BS4."""
    url = company["url"]
    name = company["name"]

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(1200)

        # Click "Phone number" para revelarlo
        try:
            phone_link = page.locator("text=Phone number").first
            if phone_link.is_visible(timeout=1200):
                phone_link.click()
                page.wait_for_timeout(1200)
        except Exception:
            pass

        html = page.content()
        return parse_detail_html(html, name, url)

    except Exception as e:
        print(f"    ERR: {e}")
        return {
            "name": name, "phone": "", "location": location_from_url(url),
            "address": "", "website": "", "services": "", "about": "", "url": url,
        }


def create_browser(p):
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    )
    page = context.new_page()
    Stealth().apply_stealth_sync(page)
    return browser, context, page


def main():
    print("=" * 60)
    print("  Scraper Angi.com - Florida (TODAS las ciudades)")
    print("  CSV:", OUTPUT_FILE)
    print("=" * 60)

    # Cargar URLs ya guardadas para continuar donde se quedó
    saved_urls = get_saved_urls()
    if saved_urls:
        print(f"  Continuando... {len(saved_urls)} empresas ya guardadas")
    else:
        if os.path.exists(OUTPUT_FILE):
            os.remove(OUTPUT_FILE)
        init_csv()

    with sync_playwright() as p:
        browser, context, page = create_browser(p)

        print(f"\n1. {len(TARGET_CITIES)} ciudades objetivo (Florida)")

        total_companies = 0
        total_with_phone = 0

        for ci, city_slug in enumerate(TARGET_CITIES):
            city_name = city_slug.replace("-", " ").title()
            print(f"\n[Ciudad {ci+1}/{len(TARGET_CITIES)}] {city_name}")

            # Obtener empresas de esta ciudad (con paginación)
            companies = collect_companies_from_city(page, city_slug)
            # Filtrar ya guardadas
            companies = [c for c in companies if c["url"] not in saved_urls]

            if not companies:
                print(f"  Sin empresas nuevas, saltando")
                continue

            print(f"  {len(companies)} empresas nuevas")

            for i, comp in enumerate(companies):
                print(f"  [{i+1}/{len(companies)}] {comp['name']}", end="")

                result = scrape_company_detail(page, comp)
                append_to_csv(result)
                saved_urls.add(comp["url"])
                total_companies += 1

                ph = result["phone"] or "---"
                print(f" -> {ph}")

                if result["phone"]:
                    total_with_phone += 1

                # Recrear browser si se cerró
                if page.is_closed():
                    print("  Recreando browser...")
                    try:
                        browser.close()
                    except Exception:
                        pass
                    try:
                        browser, context, page = create_browser(p)
                    except Exception:
                        print("  FATAL: no se pudo recrear browser")
                        browser.close()
                        return
                else:
                    page.wait_for_timeout(800)

        print(f"\n{'=' * 60}")
        print(f"  COMPLETADO")
        print(f"  Ciudades: {len(TARGET_CITIES)}")
        print(f"  Empresas: {total_companies}")
        print(f"  Con teléfono: {total_with_phone}")
        print(f"  CSV: {OUTPUT_FILE}")
        print(f"{'=' * 60}")

        browser.close()


if __name__ == "__main__":
    main()
