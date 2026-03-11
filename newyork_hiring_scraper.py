"""
Scraper de empresas que buscan SDR / Inside Sales / Appointment Setter / etc.
en Indeed, Glassdoor y LinkedIn - New York Area.
Busca phone y website visitando la página de contacto de cada empresa.
Guarda al CSV en tiempo real.
"""

import csv
import os
import re
from urllib.parse import quote_plus, urlparse
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth


OUTPUT_FILE = "hiring_newyork.csv"
FIELDNAMES = [
    "company",
    "phone",
    "email",
    "linkedin_profile",
    "website",
    "job_title",
    "location",
    "salary",
    "description",
    "source",
    "job_url",
]

SEARCH_QUERIES = [
    "SDR",
    "b2b sales",
    "Sales Development Representative",
    "real state sales",
    "sales agent",
    "Inside Sales",
    "Appointment Setter",
    "Lead Manager",
    "Cold Caller",
    "BDR",
    "Outbound Sales",
    "Lead Generation",
    "Phone Sales",
    "Bilingual Sales",
]

LOCATIONS = [
    "New York, NY",
    "Manhattan, NY",
    "Brooklyn, NY",
    "Queens, NY",
    "Bronx, NY",
    "Jersey City, NJ",
]

# locIds de Glassdoor por ciudad
GLASSDOOR_LOC_IDS = {
    "New York":   "1132348",
    "Manhattan":  "1132348",
    "Brooklyn":   "1132348",
    "Queens":     "1132348",
    "Bronx":      "1132348",
    "Jersey City": "1138207",
}


def init_csv():
    if not os.path.exists(OUTPUT_FILE) or os.path.getsize(OUTPUT_FILE) == 0:
        with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()


def append_to_csv(row):
    with open(OUTPUT_FILE, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=FIELDNAMES).writerow(row)


def get_saved_urls():
    saved = set()
    if os.path.exists(OUTPUT_FILE) and os.path.getsize(OUTPUT_FILE) > 0:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                saved.add(row.get("job_url", ""))
    return saved


def get_saved_companies_info():
    """Cache de phone/email/linkedin/website ya encontrados para no buscar de nuevo."""
    info = {}
    if os.path.exists(OUTPUT_FILE) and os.path.getsize(OUTPUT_FILE) > 0:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                c = row.get("company", "")
                if c and (row.get("phone") or row.get("website") or row.get("email")):
                    info[c] = {
                        "phone": row.get("phone", ""),
                        "email": row.get("email", ""),
                        "linkedin_profile": row.get("linkedin_profile", ""),
                        "website": row.get("website", ""),
                    }
    return info


SKIP_DOMAINS = (
    "duckduckgo",
    "google",
    "indeed",
    "glassdoor",
    "linkedin",
    "facebook",
    "yelp",
    "bbb.org",
    "twitter",
    "instagram",
    "youtube",
    "wikipedia",
    "bloomberg",
    "crunchbase",
    "ziprecruiter",
    "salary.com",
    "comparably",
    "builtin",
    "ambitionbox",
    "tiktok",
    "pinterest",
    "reddit",
    "amazon",
    "apple.com/app",
)


def extract_phone_from_html(html):
    """Extrae teléfono de HTML - primero tel: links, luego regex."""
    soup = BeautifulSoup(html, "html.parser")

    for tel_link in soup.find_all("a", href=re.compile(r"^tel:")):
        num = tel_link["href"].replace("tel:", "").strip()
        clean = re.sub(r"[^\d+]", "", num)
        if len(clean) >= 10:
            return num

    text = soup.get_text(" ", strip=True)
    phone_pattern = r"\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}"
    contact_pattern = (
        r"(?:phone|call|tel|contact|reach)[\s:.\-]*(?:us)?[\s:.\-]*" + phone_pattern
    )
    m = re.search(contact_pattern, text, re.IGNORECASE)
    if m:
        num_match = re.search(phone_pattern, m.group(0))
        if num_match:
            return num_match.group(0)

    m = re.search(phone_pattern, text)
    if m:
        return m.group(0)

    return ""


def extract_email_from_html(html):
    """Extrae email de HTML - primero mailto: links, luego regex."""
    soup = BeautifulSoup(html, "html.parser")

    for mailto in soup.find_all("a", href=re.compile(r"^mailto:")):
        email = mailto["href"].replace("mailto:", "").split("?")[0].strip()
        if "@" in email and "." in email:
            if not any(
                s in email.lower()
                for s in ["noreply", "no-reply", "donotreply", "example.com"]
            ):
                return email

    text = soup.get_text(" ", strip=True)
    m = re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)
    if m:
        email = m.group(0)
        if not any(
            s in email.lower()
            for s in ["noreply", "no-reply", "donotreply", "example.com"]
        ):
            return email

    return ""


def extract_linkedin_from_html(html, company_name):
    """Extrae perfil de LinkedIn de empresa desde el HTML del website."""
    soup = BeautifulSoup(html, "html.parser")

    for a in soup.find_all(
        "a", href=re.compile(r"linkedin\.com/company/", re.IGNORECASE)
    ):
        href = a["href"]
        if not href.startswith("http"):
            href = "https://" + href.lstrip("/")
        href = href.split("?")[0].rstrip("/")
        if "/company/" in href:
            return href

    return ""


def search_company_contact(contact_page, company_name, company_cache):
    """Busca website en DuckDuckGo, luego visita /contact del site para phone/email/linkedin."""
    if company_name in company_cache:
        return company_cache[company_name]

    phone = ""
    email = ""
    linkedin_profile = ""
    website = ""

    try:
        query = f"{company_name} official website"
        contact_page.goto(
            f"https://duckduckgo.com/?q={quote_plus(query)}",
            wait_until="domcontentloaded",
            timeout=12000,
        )
        contact_page.wait_for_timeout(2000)

        html = contact_page.content()
        soup = BeautifulSoup(html, "html.parser")

        for a in soup.find_all("a", href=True):
            h = a["href"]
            if h.startswith("http") and not any(s in h.lower() for s in SKIP_DOMAINS):
                website = h
                break
        if not website:
            for a in soup.find_all(
                "a", attrs={"data-testid": "result-extras-url-link"}
            ):
                h = a.get("href", "")
                if h.startswith("http") and not any(
                    s in h.lower() for s in SKIP_DOMAINS
                ):
                    website = h
                    break
    except Exception:
        pass

    if website:
        base = website.rstrip("/")
        parsed = urlparse(base)
        base_domain = f"{parsed.scheme}://{parsed.netloc}"

        pages_to_check = [
            f"{base_domain}/contact",
            f"{base_domain}/contact-us",
            base,
        ]

        for curl in pages_to_check:
            try:
                contact_page.goto(curl, wait_until="domcontentloaded", timeout=10000)
                contact_page.wait_for_timeout(800)
                site_html = contact_page.content()

                if not phone:
                    phone = extract_phone_from_html(site_html)
                if not email:
                    email = extract_email_from_html(site_html)
                if not linkedin_profile:
                    linkedin_profile = extract_linkedin_from_html(
                        site_html, company_name
                    )

                if phone and email and linkedin_profile:
                    break
            except Exception:
                continue

    result = {
        "phone": phone,
        "email": email,
        "linkedin_profile": linkedin_profile,
        "website": website,
    }
    company_cache[company_name] = result
    return result


def scrape_indeed(
    job_page, contact_page, query, location, saved_urls, company_cache, max_pages=5
):
    results = []

    for start in range(0, max_pages * 10, 10):
        url = (
            f"https://www.indeed.com/jobs?q={quote_plus(query)}"
            f"&l={quote_plus(location)}&start={start}"
            f"&fromage=14"
        )

        print(f"    Pag {start // 10 + 1}...", end=" ")

        try:
            job_page.goto(url, wait_until="domcontentloaded", timeout=25000)
            job_page.wait_for_timeout(1500)
        except Exception as e:
            print(f"ERR: {e}")
            break

        html = job_page.content()
        soup = BeautifulSoup(html, "html.parser")

        job_cards = soup.find_all(
            "div", class_=re.compile(r"job_seen_beacon|cardOutline")
        )
        if not job_cards:
            job_cards = soup.find_all(attrs={"data-testid": re.compile(r"job")})

        new_count = 0
        for card in job_cards:
            try:
                title_el = card.find(["h2", "h3"]) or card.find(
                    "a", class_=re.compile(r"title|jcs-JobTitle")
                )
                title = title_el.get_text(strip=True) if title_el else ""

                company_el = card.find(
                    attrs={"data-testid": "company-name"}
                ) or card.find("span", class_=re.compile(r"company|companyName"))
                company = company_el.get_text(strip=True) if company_el else ""

                loc_el = card.find(attrs={"data-testid": "text-location"}) or card.find(
                    "div", class_=re.compile(r"companyLocation")
                )
                loc = loc_el.get_text(strip=True) if loc_el else ""

                sal_el = card.find(
                    class_=re.compile(r"salary|estimated-salary|salaryText")
                )
                salary = sal_el.get_text(strip=True) if sal_el else ""

                desc_el = card.find(
                    "div", class_=re.compile(r"job-snippet|underShelfFooter")
                )
                desc = desc_el.get_text(" ", strip=True)[:300] if desc_el else ""

                link_el = card.find("a", href=re.compile(r"/rc/clk|/viewjob|/company"))
                if link_el:
                    href = link_el.get("href", "")
                    job_url = (
                        href
                        if href.startswith("http")
                        else f"https://www.indeed.com{href}"
                    )
                else:
                    jk = card.get("data-jk") or ""
                    job_url = f"https://www.indeed.com/viewjob?jk={jk}" if jk else ""

                if company and title and job_url and job_url not in saved_urls:
                    contact = search_company_contact(
                        contact_page, company, company_cache
                    )

                    row = {
                        "company": company,
                        "phone": contact["phone"],
                        "email": contact["email"],
                        "linkedin_profile": contact["linkedin_profile"],
                        "website": contact["website"],
                        "job_title": title,
                        "location": loc,
                        "salary": salary,
                        "description": desc,
                        "source": "Indeed",
                        "job_url": job_url,
                    }
                    results.append(row)
                    append_to_csv(row)
                    saved_urls.add(job_url)
                    new_count += 1

                    print(
                        f"\n      {company} | ph:{contact['phone'] or '-'} | em:{contact['email'] or '-'} | li:{contact['linkedin_profile'] or '-'}",
                        end="",
                    )

            except Exception:
                continue

        print(f" | +{new_count}")

        if new_count == 0:
            break

        job_page.wait_for_timeout(1000)

    return results


def scrape_glassdoor(
    job_page, contact_page, query, location, saved_urls, company_cache, max_pages=3
):
    results = []

    for pg in range(1, max_pages + 1):
        loc_id = GLASSDOOR_LOC_IDS.get(location, "")
        loc_id_param = f"&locId={loc_id}" if loc_id else ""
        url = (
            f"https://www.glassdoor.com/Job/jobs.htm"
            f"?sc.keyword={quote_plus(query)}"
            f"&locT=C&locKeyword={quote_plus(location)}"
            f"{loc_id_param}"
            f"&fromAge=14&p={pg}"
        )

        print(f"    Pag {pg}...", end=" ")

        try:
            job_page.goto(url, wait_until="domcontentloaded", timeout=25000)
            job_page.wait_for_timeout(3000)
        except Exception as e:
            print(f"ERR: {e}")
            break

        html = job_page.content()
        soup = BeautifulSoup(html, "html.parser")

        job_cards = soup.find_all("li", class_=re.compile(r"JobsList_jobListItem"))
        if not job_cards:
            job_cards = soup.find_all("div", class_=re.compile(r"jobCard|JobCard"))

        new_count = 0
        for card in job_cards:
            try:
                title_el = card.find(class_=re.compile(r"jobTitle|JobCard_jobTitle"))
                title = title_el.get_text(strip=True) if title_el else ""

                company_el = card.find(class_=re.compile(r"EmployerProfile|employer"))
                company = company_el.get_text(strip=True) if company_el else ""

                loc_el = card.find(class_=re.compile(r"location|JobCard_location"))
                loc = loc_el.get_text(strip=True) if loc_el else ""

                sal_el = card.find(class_=re.compile(r"salary|SalaryEstimate"))
                salary = sal_el.get_text(strip=True) if sal_el else ""

                link_el = card.find("a", href=True)
                job_url = ""
                if link_el:
                    href = link_el["href"]
                    job_url = (
                        href
                        if href.startswith("http")
                        else f"https://www.glassdoor.com{href}"
                    )

                if company and title and job_url and job_url not in saved_urls:
                    contact = search_company_contact(
                        contact_page, company, company_cache
                    )

                    row = {
                        "company": company,
                        "phone": contact["phone"],
                        "email": contact["email"],
                        "linkedin_profile": contact["linkedin_profile"],
                        "website": contact["website"],
                        "job_title": title,
                        "location": loc,
                        "salary": salary,
                        "description": "",
                        "source": "Glassdoor",
                        "job_url": job_url,
                    }
                    results.append(row)
                    append_to_csv(row)
                    saved_urls.add(job_url)
                    new_count += 1

            except Exception:
                continue

        print(f"+{new_count}")

        if new_count == 0:
            break

        job_page.wait_for_timeout(1500)

    return results


def scrape_linkedin(
    job_page, contact_page, query, location, saved_urls, company_cache, max_pages=3
):
    """Scrape LinkedIn Jobs (público, sin login)."""
    results = []

    for pg in range(max_pages):
        start = pg * 25
        url = (
            f"https://www.linkedin.com/jobs/search/"
            f"?keywords={quote_plus(query)}"
            f"&location={quote_plus(location)}"
            f"&f_TPR=r604800"
            f"&start={start}"
        )

        print(f"    Pag {pg + 1}...", end=" ")

        try:
            job_page.goto(url, wait_until="domcontentloaded", timeout=25000)
            job_page.wait_for_timeout(2500)

            job_page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            job_page.wait_for_timeout(1500)
        except Exception as e:
            print(f"ERR: {e}")
            break

        html = job_page.content()
        soup = BeautifulSoup(html, "html.parser")

        job_cards = soup.find_all(
            "div", class_=re.compile(r"base-card|job-search-card")
        )
        if not job_cards:
            job_cards = soup.find_all("li", class_=re.compile(r"jobs-search__result"))

        new_count = 0
        for card in job_cards:
            try:
                title_el = card.find(
                    class_=re.compile(r"base-search-card__title|job-card-list__title")
                )
                title = title_el.get_text(strip=True) if title_el else ""

                company_el = card.find(
                    class_=re.compile(
                        r"base-search-card__subtitle|job-card-container__company"
                    )
                )
                company = company_el.get_text(strip=True) if company_el else ""

                loc_el = card.find(
                    class_=re.compile(
                        r"job-search-card__location|job-card-container__metadata"
                    )
                )
                loc = loc_el.get_text(strip=True) if loc_el else ""

                link_el = card.find("a", href=re.compile(r"linkedin.com/jobs/view"))
                job_url = ""
                if link_el:
                    job_url = link_el.get("href", "").split("?")[0]

                if company and title and job_url and job_url not in saved_urls:
                    contact = search_company_contact(
                        contact_page, company, company_cache
                    )

                    row = {
                        "company": company,
                        "phone": contact["phone"],
                        "email": contact["email"],
                        "linkedin_profile": contact["linkedin_profile"],
                        "website": contact["website"],
                        "job_title": title,
                        "location": loc,
                        "salary": "",
                        "description": "",
                        "source": "LinkedIn",
                        "job_url": job_url,
                    }
                    results.append(row)
                    append_to_csv(row)
                    saved_urls.add(job_url)
                    new_count += 1

            except Exception:
                continue

        print(f"+{new_count}")

        if new_count == 0:
            break

        job_page.wait_for_timeout(1500)

    return results


def create_browser(p):
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(
        viewport={"width": 1280, "height": 800},
        locale="en-US",
        timezone_id="America/New_York",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    )
    job_page = context.new_page()
    contact_page = context.new_page()
    Stealth().apply_stealth_sync(job_page)
    Stealth().apply_stealth_sync(contact_page)
    return browser, context, job_page, contact_page


def main():
    print("=" * 60)
    print("  Scraper: Empresas contratando SDR/Sales/Callers")
    print("  Zona: New York Area")
    print("  Fuentes: Indeed + Glassdoor + LinkedIn")
    print("  Phone: desde /contact del website real")
    print("  CSV:", OUTPUT_FILE)
    print("=" * 60)

    saved_urls = get_saved_urls()
    company_cache = get_saved_companies_info()
    if saved_urls:
        print(f"  {len(saved_urls)} jobs ya guardados")
    if company_cache:
        print(f"  {len(company_cache)} empresas con contacto en cache")

    if not saved_urls:
        if os.path.exists(OUTPUT_FILE):
            os.remove(OUTPUT_FILE)
    init_csv()

    with sync_playwright() as p:
        browser, context, job_page, contact_page = create_browser(p)

        total = 0

        print("\n" + "=" * 40)
        print("  GLASSDOOR")
        print("=" * 40)

        for query in SEARCH_QUERIES:
            for location in LOCATIONS:
                city = location.split(",")[0]
                print(f"\n  [{query}] en [{city}]")
                try:
                    results = scrape_glassdoor(
                        job_page, contact_page, query, city, saved_urls, company_cache
                    )
                    total += len(results)
                    print(f"  -> {len(results)} nuevos")
                except Exception as e:
                    print(f"  ERR: {e}")

                if job_page.is_closed():
                    try:
                        browser.close()
                    except Exception:
                        pass
                    browser, context, job_page, contact_page = create_browser(p)

        print("\n" + "=" * 40)
        print("  INDEED")
        print("=" * 40)

        for query in SEARCH_QUERIES:
            for location in LOCATIONS:
                print(f"\n  [{query}] en [{location}]")
                try:
                    results = scrape_indeed(
                        job_page,
                        contact_page,
                        query,
                        location,
                        saved_urls,
                        company_cache,
                    )
                    total += len(results)
                    print(f"  -> {len(results)} nuevos")
                except Exception as e:
                    print(f"  ERR: {e}")

                if job_page.is_closed():
                    try:
                        browser.close()
                    except Exception:
                        pass
                    browser, context, job_page, contact_page = create_browser(p)

        print("\n" + "=" * 40)
        print("  LINKEDIN")
        print("=" * 40)

        for query in SEARCH_QUERIES:
            for location in LOCATIONS:
                print(f"\n  [{query}] en [{location}]")
                try:
                    results = scrape_linkedin(
                        job_page,
                        contact_page,
                        query,
                        location,
                        saved_urls,
                        company_cache,
                    )
                    total += len(results)
                    print(f"  -> {len(results)} nuevos")
                except Exception as e:
                    print(f"  ERR: {e}")

                if job_page.is_closed():
                    try:
                        browser.close()
                    except Exception:
                        pass
                    browser, context, job_page, contact_page = create_browser(p)

        print(f"\n{'=' * 60}")
        print(f"  COMPLETADO: {total} empresas nuevas")
        print(f"  Total en CSV: {len(saved_urls)}")
        print(f"{'=' * 60}")

        if os.path.exists(OUTPUT_FILE):
            companies = {}
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    c = row.get("company", "")
                    if c:
                        companies[c] = companies.get(c, 0) + 1

            top = sorted(companies.items(), key=lambda x: -x[1])[:20]
            if top:
                print("\n  TOP 20 empresas que más contratan:")
                for i, (name, count) in enumerate(top):
                    ph = company_cache.get(name, {}).get("phone", "")
                    ph_str = f" | {ph}" if ph else ""
                    print(f"    {i+1}. {name} ({count} postings){ph_str}")

        browser.close()


if __name__ == "__main__":
    main()
