"""
Scraper de empresas desde Angi.com (New York)
Recorre TODAS las ciudades de NY, extrae empresas con:
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


BASE_URL = "https://www.angi.com/companylist/us/ny/"
OUTPUT_FILE = "angie_companies_ny.csv"
FIELDNAMES = ["name", "phone", "location", "address", "website", "services", "about", "url"]

# Ciudades de New York State — ordenadas de mayor a menor población/importancia
TARGET_CITIES = [
    # =========================================================
    # 1. NEW YORK CITY — los 5 boroughs primero (más leads)
    # =========================================================
    "new-york", "brooklyn", "queens", "bronx", "staten-island",

    # --- Manhattan (barrios clave) ---
    "manhattan", "harlem", "upper-west-side", "upper-east-side",
    "midtown", "hell-kitchen", "chelsea", "gramercy", "murray-hill",
    "east-village", "west-village", "greenwich-village",
    "soho", "tribeca", "financial-district", "lower-east-side",
    "washington-heights", "inwood",

    # --- Brooklyn (barrios clave) ---
    "williamsburg", "bushwick", "bed-stuy", "crown-heights",
    "flatbush", "east-flatbush", "park-slope", "sunset-park",
    "bensonhurst", "bay-ridge", "sheepshead-bay", "brighton-beach",
    "coney-island", "canarsie", "east-new-york", "brownsville",
    "fort-greene", "clinton-hill", "downtown-brooklyn",
    "greenpoint", "ridgewood", "midwood",

    # --- Queens (barrios clave) ---
    "flushing", "jamaica", "astoria", "jackson-heights",
    "corona", "elmhurst", "woodside", "forest-hills",
    "long-island-city", "rego-park", "ozone-park",
    "richmond-hill", "springfield-gardens", "far-rockaway",
    "howard-beach", "sunnyside",

    # --- Bronx (barrios clave) ---
    "fordham", "mott-haven", "soundview", "co-op-city",
    "pelham-bay", "riverdale", "tremont", "highbridge",
    "hunts-point", "parkchester",

    # =========================================================
    # 2. CIUDADES GRANDES UPSTATE — por población
    # =========================================================
    "buffalo",          # ~280k hab
    "rochester",        # ~210k hab
    "yonkers",          # ~200k hab (Westchester)
    "syracuse",         # ~145k hab
    "albany",           # ~100k hab
    "new-rochelle",     # ~80k hab
    "mount-vernon",     # ~70k hab
    "schenectady",      # ~65k hab
    "utica",            # ~60k hab
    "white-plains",     # ~58k hab
    "troy",             # ~50k hab
    "binghamton",       # ~45k hab
    "niagara-falls",    # ~44k hab
    "poughkeepsie",     # ~32k hab
    "ithaca",           # ~30k hab
    "kingston",         # ~23k hab
    "saratoga-springs", # ~28k hab
    "watertown",        # ~26k hab
    "elmira",           # ~25k hab
    "plattsburgh",      # ~20k hab
    "jamestown",        # ~28k hab
    "glens-falls",      # ~15k hab
    "newburgh",         # ~28k hab

    # =========================================================
    # 3. LONG ISLAND — Nassau y Suffolk (alta densidad)
    # =========================================================
    # Nassau County (más poblado)
    "hempstead", "levittown", "hicksville", "east-meadow",
    "garden-city", "mineola", "westbury", "uniondale",
    "elmont", "valley-stream", "rockville-centre", "freeport",
    "new-hyde-park", "great-neck", "port-washington",
    "manhasset", "roslyn", "glen-cove", "oyster-bay",
    "massapequa", "massapequa-park", "seaford", "wantagh",
    "bellmore", "merrick", "baldwin", "lynbrook",
    "farmingdale", "bethpage", "plainview", "syosset",
    "woodbury", "jericho",

    # Suffolk County
    "brentwood", "central-islip", "bay-shore", "islip",
    "huntington", "huntington-station", "commack",
    "hauppauge", "smithtown", "ronkonkoma", "holbrook",
    "centereach", "selden", "coram", "medford",
    "patchogue", "lindenhurst", "amityville", "copiague",
    "babylon", "riverhead", "southampton", "east-hampton",
    "port-jefferson", "stony-brook", "northport",

    # =========================================================
    # 4. WESTCHESTER COUNTY
    # =========================================================
    "mount-kisco", "ossining", "peekskill", "harrison", "rye",
    "mamaroneck", "larchmont", "bronxville", "tuckahoe",
    "eastchester", "tarrytown", "sleepy-hollow", "pleasantville",
    "port-chester", "scarsdale", "armonk",

    # =========================================================
    # 5. ROCKLAND & ORANGE COUNTY
    # =========================================================
    "spring-valley", "new-city", "nyack", "suffern", "pearl-river",
    "nanuet", "haverstraw",
    "middletown", "port-jervis", "cornwall", "monroe",
    "goshen", "warwick",
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
    match = re.search(r"/us/ny/([^/]+)/", url)
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
            if ".htm" in href and "/companylist/us/ny/" in href and 2 < len(name) < 120:
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
    print("  Scraper Angi.com - New York (TODAS las ciudades)")
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

        print(f"\n1. {len(TARGET_CITIES)} ciudades objetivo (New York)")

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
