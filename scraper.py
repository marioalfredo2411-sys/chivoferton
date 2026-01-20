"""
Encuentra24 Housing Scraper
Scrapes 100 listings (50 Sale + 50 Rent) with detailed specs, descriptions, images.
Saves results to sample.json.
"""
import requests
from bs4 import BeautifulSoup
import json
import re
import time

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

BASE_URL = "https://www.encuentra24.com"
SALE_URL = "https://www.encuentra24.com/el-salvador-es/bienes-raices-venta-de-propiedades-casas"
RENT_URL = "https://www.encuentra24.com/el-salvador-es/bienes-raices-alquiler-casas"


def make_absolute_url(href):
    """Convert relative URL to absolute URL."""
    if href.startswith("http"):
        return href
    return BASE_URL + href


def get_listing_urls(base_url, max_listings=50):
    """Collect listing URLs from search result pages."""
    urls = []
    page = 1
    while len(urls) < max_listings:
        url = base_url if page == 1 else f"{base_url}.{page}"
        print(f"  Fetching page {page}: {url}")
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")
            links = soup.select("a.d3-ad-tile__description")
            if not links:
                print(f"  No listings found on page {page}, stopping.")
                break
            for link in links:
                href = link.get("href")
                if href:
                    absolute_url = make_absolute_url(href)
                    if absolute_url not in urls:
                        urls.append(absolute_url)
                        if len(urls) >= max_listings:
                            break
            page += 1
            time.sleep(0.5)  # Be polite
        except Exception as e:
            print(f"  Error fetching page {page}: {e}")
            break
    return urls[:max_listings]


def parse_specs(soup):
    """Extract specs as a structured object."""
    specs = {}
    # Try the summary insight attributes first
    for item in soup.select(".d3-property-insight__attribute"):
        label_el = item.select_one(".d3-property-insight__attribute-title")
        value_el = item.select_one(".d3-property-insight__attribute-value")
        if label_el and value_el:
            label = label_el.get_text(strip=True).lower()
            value = value_el.get_text(strip=True)
            if "área" in label or "m²" in label or "construida" in label:
                specs["area"] = value
            elif "recámaras" in label or "habitaciones" in label:
                specs["bedrooms"] = value
            elif "baños" in label:
                specs["bathrooms"] = value
            elif "estacionamientos" in label or "parqueo" in label:
                specs["parking"] = value
            elif "precio" in label:
                specs["price_per_m2"] = value
    
    # Fallback: check for spec items with icons
    for item in soup.select(".d3-ad-tile__details-item"):
        use_el = item.select_one("use")
        value_el = item.select_one("span")
        if use_el and value_el:
            href = use_el.get("xlink:href", "")
            value = value_el.get_text(strip=True)
            if "#resize" in href:
                specs["area"] = value
            elif "#bed" in href:
                specs["bedrooms"] = value
            elif "#bath" in href:
                specs["bathrooms"] = value
            elif "#parking" in href:
                specs["parking"] = value
    return specs


def parse_details(soup):
    """Extract additional details as key-value pairs."""
    details = {}
    for item in soup.select(".d3-property-details__detail"):
        label_el = item.select_one(".d3-property-details__detail-label")
        if label_el:
            label = label_el.get_text(strip=True)
            # Value is the remaining text after the label
            full_text = item.get_text(strip=True)
            value = full_text.replace(label, "", 1).strip()
            if label and value:
                details[label] = value
    return details


def parse_images(soup):
    """Extract all image URLs from the listing gallery."""
    images = []
    
    # Method 1: Look for gallery images in data attributes or img tags
    for img in soup.select(".d3-gallery img, .gallery-image img, .swiper-slide img, [data-src]"):
        src = img.get("data-src") or img.get("src") or ""
        if src and "photos.encuentra24.com" in src:
            # Clean up the URL to get the full-size version
            images.append(src)
        elif src and src.startswith("http"):
            images.append(src)
    
    # Method 2: Look for image URLs in script tags (often in JSON)
    for script in soup.select("script"):
        script_text = script.string or ""
        # Find all encuentra24 photo URLs
        photo_urls = re.findall(r'https://photos\.encuentra24\.com[^"\'\\s]+', script_text)
        for url in photo_urls:
            if url not in images:
                images.append(url)
    
    # Method 3: Look for data-gallery or similar attributes
    for el in soup.select("[data-gallery], [data-images], [data-photo]"):
        data = el.get("data-gallery") or el.get("data-images") or el.get("data-photo") or ""
        photo_urls = re.findall(r'https://photos\.encuentra24\.com[^"\'\\s\]]+', data)
        for url in photo_urls:
            if url not in images:
                images.append(url)
    
    # Deduplicate while preserving order
    seen = set()
    unique_images = []
    for img in images:
        # Clean URL (remove escaped characters)
        img = img.replace("\\u002F", "/").replace("\\/", "/")
        if img not in seen:
            seen.add(img)
            unique_images.append(img)
    
    return unique_images


def scrape_listing(url, listing_type):
    """Scrape a single listing page."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")

        # Title
        title_el = soup.select_one("h1") or soup.select_one("title")
        title = title_el.get_text(strip=True) if title_el else ""

        # Price
        price_el = soup.select_one(".estate-price") or soup.select_one(".d3-price")
        price = price_el.get_text(strip=True) if price_el else ""
        if not price:
            # Fallback: search for price pattern
            match = re.search(r"\$[\d,\.]+", soup.get_text())
            price = match.group(0) if match else ""

        # Specs
        specs = parse_specs(soup)

        # Details (contains Localización and Publicado)
        details = parse_details(soup)
        
        # Extract Location from details (Localización)
        location = details.get("Localización", "")
        if not location:
            # Fallback to DOM element
            location_el = soup.select_one(".d3-location") or soup.select_one(".location")
            location = location_el.get_text(strip=True) if location_el else ""
        
        # Extract Publication Date from details (Publicado)
        published_date = details.get("Publicado", "")

        # Description
        desc_el = soup.select_one(".d3-property-about__text") or soup.select_one(".d3-property-description__content")
        description = desc_el.get_text(strip=True) if desc_el else ""

        # Images
        images = parse_images(soup)

        # External ID from URL
        external_id = url.rstrip("/").split("/")[-1]

        return {
            "title": title,
            "price": price,
            "location": location,
            "published_date": published_date,
            "listing_type": listing_type,
            "url": url,
            "external_id": external_id,
            "specs": specs,
            "details": details,
            "description": description,
            "images": images
        }
    except Exception as e:
        print(f"  Error scraping {url}: {e}")
        return None


def main():
    all_listings = []

    # --- SALE LISTINGS ---
    print("\n=== Scraping SALE Listings ===")
    sale_urls = get_listing_urls(SALE_URL, max_listings=50)
    print(f"Found {len(sale_urls)} sale URLs. Scraping details...")
    for i, url in enumerate(sale_urls, 1):
        print(f"  [{i}/{len(sale_urls)}] {url[:80]}...")
        data = scrape_listing(url, "sale")
        if data:
            all_listings.append(data)
        time.sleep(0.3)

    # --- RENT LISTINGS ---
    print("\n=== Scraping RENT Listings ===")
    rent_urls = get_listing_urls(RENT_URL, max_listings=50)
    print(f"Found {len(rent_urls)} rent URLs. Scraping details...")
    for i, url in enumerate(rent_urls, 1):
        print(f"  [{i}/{len(rent_urls)}] {url[:80]}...")
        data = scrape_listing(url, "rent")
        if data:
            all_listings.append(data)
        time.sleep(0.3)

    # --- SAVE ---
    output_file = "sample.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_listings, f, ensure_ascii=False, indent=2)

    print(f"\n=== DONE ===")
    print(f"Total listings scraped: {len(all_listings)}")
    print(f"Saved to: {output_file}")


if __name__ == "__main__":
    main()
