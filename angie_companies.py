"""
Scraper de empresas desde Angi.com (California)
Recorre TODAS las ciudades de CA, extrae empresas con:
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


BASE_URL = "https://www.angi.com/companylist/us/ca/"
OUTPUT_FILE = "angie_companies.csv"
FIELDNAMES = ["name", "phone", "location", "address", "website", "services", "about", "url"]

# Ciudades grandes de LA y Bay Area
TARGET_CITIES = [
    # --- LOS ANGELES METRO ---
    "los-angeles", "long-beach", "santa-monica", "burbank", "glendale",
    "pasadena", "torrance", "inglewood", "downey", "west-hollywood",
    "beverly-hills", "culver-city", "el-monte", "compton", "norwalk",
    "whittier", "alhambra", "lakewood", "bellflower", "arcadia",
    "redondo-beach", "carson", "west-covina", "pomona", "montebello",
    "monterey-park", "south-gate", "huntington-park", "covina", "azusa",
    "glendora", "san-dimas", "la-verne", "diamond-bar", "rowland-heights",
    "hacienda-heights", "la-mirada", "cerritos", "hermosa-beach",
    "manhattan-beach", "el-segundo", "gardena", "hawthorne", "lawndale",
    "paramount", "pico-rivera", "santa-fe-springs", "la-puente",
    "baldwin-park", "irwindale", "duarte", "monrovia", "temple-city",
    "san-gabriel", "rosemead", "south-pasadena", "eagle-rock",
    "highland-park", "silver-lake", "echo-park", "koreatown",
    "hollywood", "studio-city", "sherman-oaks", "encino", "tarzana",
    "woodland-hills", "canoga-park", "chatsworth", "northridge",
    "granada-hills", "sylmar", "sun-valley", "north-hollywood",
    "van-nuys", "reseda", "panorama-city", "west-hills", "calabasas",
    "agoura-hills", "thousand-oaks", "simi-valley", "moorpark",
    "camarillo", "oxnard", "ventura", "santa-clarita", "valencia",
    "palmdale", "lancaster",
    # --- ORANGE COUNTY ---
    "anaheim", "santa-ana", "irvine", "huntington-beach", "garden-grove",
    "orange", "fullerton", "costa-mesa", "mission-viejo", "lake-forest",
    "newport-beach", "laguna-beach", "san-clemente", "tustin", "brea",
    "yorba-linda", "placentia", "la-habra", "buena-park", "cypress",
    "fountain-valley", "westminster", "stanton", "laguna-niguel",
    "aliso-viejo", "rancho-santa-margarita", "dana-point",
    # --- SAN FRANCISCO BAY AREA ---
    "san-francisco", "oakland", "san-jose", "berkeley", "fremont",
    "hayward", "sunnyvale", "santa-clara", "concord", "richmond",
    "daly-city", "san-mateo", "redwood-city", "mountain-view",
    "palo-alto", "milpitas", "union-city", "newark", "pleasanton",
    "livermore", "dublin", "san-ramon", "walnut-creek", "danville",
    "lafayette", "orinda", "moraga", "alameda", "san-leandro",
    "castro-valley", "san-lorenzo", "foster-city", "belmont",
    "san-carlos", "menlo-park", "atherton", "woodside", "half-moon-bay",
    "pacifica", "south-san-francisco", "burlingame", "san-bruno",
    "millbrae", "saratoga", "los-gatos", "campbell", "cupertino",
    "santa-cruz", "capitola", "scotts-valley", "gilroy", "morgan-hill",
    "vallejo", "benicia", "martinez", "antioch", "pittsburg",
    "brentwood", "oakley", "hercules", "pinole", "el-cerrito",
    "san-rafael", "novato", "mill-valley", "sausalito", "tiburon",
    "larkspur", "corte-madera", "fairfax", "san-anselmo",
    "petaluma", "santa-rosa", "napa", "sonoma",
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
    match = re.search(r"/us/ca/([^/]+)/", url)
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
            if ".htm" in href and "/companylist/us/ca/" in href and 2 < len(name) < 120:
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
    print("  Scraper Angi.com - California (TODAS las ciudades)")
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

        # Paso 1: Recorrer ciudades grandes de LA + Bay Area
        print(f"\n1. {len(TARGET_CITIES)} ciudades objetivo (LA + Bay Area)")

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
