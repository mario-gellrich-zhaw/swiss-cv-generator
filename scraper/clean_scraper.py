
import os
import re
import time
import random
import logging
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup, Tag
from requests import RequestException
from dotenv import load_dotenv


# Load environment variables at the start
load_dotenv()

OVERVIEW_URL = "https://www.berufsberatung.ch/dyn/show/1893"
DETAIL_PATH_HINT = "/dyn/show/1900"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept-Language": "de-CH,de;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

REQUEST_TIMEOUT_SECONDS = 25
RETRY_COUNT = 2
SLEEP_BETWEEN_REQUESTS_SECONDS = (0.8, 1.6)


def get_mongodb_config() -> Dict[str, str]:
    """Get MongoDB configuration from .env file"""
    config = {
        "uri": os.getenv("MONGODB_URI", "mongodb://localhost:27017"),
        "database": os.getenv("MONGODB_DB", os.getenv("MONGODB_DATABASE", "ds_project")),
        "collection": "cv_berufsberatung"
    }

    uri_safe = config["uri"].split("@")[-1] if "@" in config["uri"] else config["uri"]
    logging.info(f"MongoDB Config - URI: ...{uri_safe}, DB: {config['database']}, Collection: {config['collection']}")

    return config


def test_mongodb_connection() -> bool:
    """Test MongoDB connection using .env configuration"""
    try:
        config = get_mongodb_config()

        pymongo = __import__("pymongo")
        MongoClient = getattr(pymongo, "MongoClient")

        client = MongoClient(config["uri"], serverSelectionTimeoutMS=5000)
        client.admin.command('ismaster')

        db = client[config["database"]]
        collection = db[config["collection"]]

        test_doc = {"_test": True, "timestamp": time.time()}
        collection.insert_one(test_doc)
        collection.delete_one({"_test": True})

        client.close()
        return True

    except ImportError:
        logging.error("pymongo not installed. Run: pip install pymongo python-dotenv")
        return False
    except Exception as e:
        logging.error(f"MongoDB connection error: {e}")
        return False


def sleep_with_jitter() -> None:
    time.sleep(random.uniform(*SLEEP_BETWEEN_REQUESTS_SECONDS))


def http_get(url: str) -> Optional[str]:
    last_exc: Optional[Exception] = None
    for attempt in range(RETRY_COUNT + 1):
        try:
            resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
            resp.raise_for_status()
            return resp.text
        except RequestException as exc:
            last_exc = exc
            if attempt < RETRY_COUNT:
                sleep_with_jitter()

    logging.warning("GET failed %s: %s", url, last_exc)
    return None


def normalize_text(text: str) -> str:
    """Enhanced text normalization with better formatting"""
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    text = re.sub(r"([.!?])([A-Z])", r"\1 \2", text)
    return text


def extract_title_and_description(soup: BeautifulSoup) -> Tuple[str, str]:
    """Extract title and description from roof-top section"""
    title = ""
    description = ""

    roof_top = soup.find("div", id="roof-top")
    if roof_top:
        h1 = roof_top.find("h1")
        if h1:
            title = normalize_text(h1.get_text())
            if title.lower().startswith("zum "):
                title = ""

        lead_p = roof_top.find("p", class_="lead")
        if lead_p:
            description = normalize_text(lead_p.get_text())

    if not title:
        for h1 in soup.find_all("h1"):
            title_text = normalize_text(h1.get_text())
            if title_text and not title_text.lower().startswith("zum ") and len(title_text) > 5:
                title = title_text
                break

    return title, description


def extract_categories(soup: BeautifulSoup) -> Dict[str, str]:
    """Extract categories with improved formatting"""
    categories = {}

    roof_bottom = soup.find("div", id="roof-bottom")
    if roof_bottom:
        toggle_box = roof_bottom.find("div", class_="toggleBox")
        if toggle_box:
            box_content = toggle_box.find("div", class_="boxContent")
            if box_content:
                dl_element = box_content.find("dl")
                if dl_element:
                    dt_elements = dl_element.find_all("dt")
                    dd_elements = dl_element.find_all("dd")

                    for dt, dd in zip(dt_elements, dd_elements):
                        key = normalize_text(dt.get_text()).lower()
                        value = normalize_text(dd.get_text())
                        categories[key] = value

                update_elem = box_content.find("p", class_="eDoc")
                if update_elem:
                    update_text = normalize_text(update_elem.get_text())
                    date_match = re.search(r"(\d{1,2}\.\d{1,2}\.\d{4})", update_text)
                    if date_match:
                        categories["aktualisiert"] = date_match.group(1)
                    else:
                        categories["aktualisiert"] = update_text

    return categories


def extract_apprenticeship_info(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract apprenticeship addresses and available positions info"""
    apprenticeship_info = {
        "schnupperanfragen_count": 0,
        "schnupperanfragen_url": "",
        "freie_lehrstellen_count": 0,
        "freie_lehrstellen_url": ""
    }

    buttonbox = soup.find("div", class_="buttonbox")
    if buttonbox:
        buttons = buttonbox.find_all("a", class_="ux-button")

        for button in buttons:
            text = normalize_text(button.get_text())
            href = button.get("href", "")

            numbers = re.findall(r"\d+", text)

            if "schnupperanfragen" in text.lower():
                if numbers:
                    apprenticeship_info["schnupperanfragen_count"] = int(numbers[0])
                if href:
                    apprenticeship_info["schnupperanfragen_url"] = href

            elif "freie lehrstellen" in text.lower():
                if numbers:
                    apprenticeship_info["freie_lehrstellen_count"] = int(numbers[0])
                if href:
                    apprenticeship_info["freie_lehrstellen_url"] = href

    return apprenticeship_info


def extract_taetigkeiten(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract activities with improved structure"""
    taetigkeiten = {
        "beschreibung": "",
        "kategorien": {},
        "summary_stats": {}
    }

    anchor_element = soup.find(id="anchor1")
    if not anchor_element:
        return taetigkeiten

    toggle_box = anchor_element.find_parent("div", class_="toggleBox")
    if not toggle_box:
        return taetigkeiten

    box_content = toggle_box.find("div", class_="boxContent")
    if not box_content:
        return taetigkeiten

    first_p = box_content.find("p")
    if first_p:
        taetigkeiten["beschreibung"] = normalize_text(first_p.get_text())

    current_category = None
    current_activities = []
    total_activities = 0

    for element in box_content.find_all(["h4", "ul", "li"]):
        if element.name == "h4":
            if current_category and current_activities:
                taetigkeiten["kategorien"][current_category] = current_activities
                total_activities += len(current_activities)

            current_category = normalize_text(element.get_text())
            current_activities = []

        elif element.name == "ul" and current_category:
            for li in element.find_all("li", recursive=False):
                activity = normalize_text(li.get_text())
                if activity:
                    current_activities.append(activity)

    if current_category and current_activities:
        taetigkeiten["kategorien"][current_category] = current_activities
        total_activities += len(current_activities)

    taetigkeiten["summary_stats"] = {
        "total_categories": len(taetigkeiten["kategorien"]),
        "total_activities": total_activities
    }

    return taetigkeiten


def extract_ausbildung(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract detailed education information with validation"""
    ausbildung = {
        # Vocational fields
        "bildung_berufliche_praxis": "",
        "schulische_bildung": "",
        "ueberbetriebliche_kurse": "",
        "dauer": "",
        "dauer_jahre": 0,
        "inhalt": [],
        "berufsmaturitaet": "",
        "abschluss": "",
        "bildungstyp": "EFZ",

        # Academic fields
        "grundlage": "",
        "studienort": "",
        "studienaufbau": "",
        "bachelorstudium": "",
        "masterstudium": ""
    }

    anchor_element = soup.find(id="anchor2")
    if not anchor_element:
        return ausbildung

    toggle_box = anchor_element.find_parent("div", class_="toggleBox")
    if not toggle_box:
        return ausbildung

    box_content = toggle_box.find("div", class_="boxContent")
    if not box_content:
        return ausbildung

    current_section = None

    for element in box_content.find_all(["h3", "p", "ul", "li"]):
        if element.name == "h3":
            section_title = normalize_text(element.get_text()).lower()

            # Vocational education sections
            if "bildung in beruflicher praxis" in section_title:
                current_section = "bildung_berufliche_praxis"
            elif "schulische bildung" in section_title:
                current_section = "schulische_bildung"  
            elif "überbetriebliche kurse" in section_title:
                current_section = "ueberbetriebliche_kurse"
            elif "dauer" in section_title:
                current_section = "dauer"
            elif "inhalt" in section_title:
                current_section = "inhalt"
            elif "berufsmaturität" in section_title:
                current_section = "berufsmaturitaet"
            elif "abschluss" in section_title:
                current_section = "abschluss"

            # Academic sections
            elif "grundlage" in section_title:
                current_section = "grundlage"
            elif "studienort" in section_title:
                current_section = "studienort"
            elif "studienaufbau" in section_title:
                current_section = "studienaufbau"
            elif "bachelorstudium" in section_title or ("bachelor" in section_title and "studium" in section_title):
                current_section = "bachelorstudium"
            elif "masterstudium" in section_title or ("master" in section_title and "studium" in section_title):
                current_section = "masterstudium"
            else:
                current_section = None

        elif element.name == "p" and current_section:
            text = normalize_text(element.get_text())
            if text:
                if current_section == "inhalt":
                    continue
                else:
                    ausbildung[current_section] = text

                    if current_section == "dauer":
                        duration_match = re.search(r"(\d+)\s*jahre?", text.lower())
                        if duration_match:
                            ausbildung["dauer_jahre"] = int(duration_match.group(1))

                    if current_section == "abschluss":
                        if "EBA" in text:
                            ausbildung["bildungstyp"] = "EBA"
                        elif "EFZ" in text:
                            ausbildung["bildungstyp"] = "EFZ"
                        elif any(x in text for x in ["Bachelor", "Master", "ETH", "Universität", "Hochschule"]):
                            ausbildung["bildungstyp"] = "Hochschule"

        elif element.name == "ul" and current_section == "inhalt":
            for li in element.find_all("li", recursive=False):
                item_text = normalize_text(li.get_text())
                if item_text:
                    ausbildung["inhalt"].append(item_text)

    return ausbildung


def extract_voraussetzungen(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract requirements with enhanced structure"""
    voraussetzungen = {
        "vorbildung": [],
        "anforderungen": [],
        "kategorisierte_anforderungen": {
            "physische_anforderungen": [],
            "fachliche_faehigkeiten": [],
            "persoenliche_eigenschaften": []
        }
    }

    anchor_element = soup.find(id="anchor3")
    if not anchor_element:
        return voraussetzungen

    toggle_box = anchor_element.find_parent("div", class_="toggleBox")
    if not toggle_box:
        return voraussetzungen

    box_content = toggle_box.find("div", class_="boxContent")
    if not box_content:
        return voraussetzungen

    current_section = None

    for element in box_content.find_all(["h3", "ul", "li", "p"]):
        if element.name == "h3":
            section_title = normalize_text(element.get_text()).lower()
            if "vorbildung" in section_title:
                current_section = "vorbildung"
            elif "anforderungen" in section_title:
                current_section = "anforderungen"
            else:
                current_section = None

        elif element.name == "ul" and current_section:
            for li in element.find_all("li", recursive=False):
                item_text = normalize_text(li.get_text())
                if item_text:
                    voraussetzungen[current_section].append(item_text)

        elif element.name == "p" and current_section == "vorbildung":
            text = normalize_text(element.get_text())
            if text and text not in voraussetzungen["vorbildung"]:
                voraussetzungen["vorbildung"].append(text)

    # Categorize requirements
    physische_keywords = ["schwindelfreiheit", "körperliche", "fitness", "kraft", "ausdauer"]
    fachliche_keywords = ["geschick", "verständnis", "vorstellungsvermögen", "kenntnisse", "fähigkeiten"]

    for anforderung in voraussetzungen["anforderungen"]:
        anforderung_lower = anforderung.lower()
        if any(keyword in anforderung_lower for keyword in physische_keywords):
            voraussetzungen["kategorisierte_anforderungen"]["physische_anforderungen"].append(anforderung)
        elif any(keyword in anforderung_lower for keyword in fachliche_keywords):
            voraussetzungen["kategorisierte_anforderungen"]["fachliche_faehigkeiten"].append(anforderung)
        else:
            voraussetzungen["kategorisierte_anforderungen"]["persoenliche_eigenschaften"].append(anforderung)

    return voraussetzungen


def extract_weiterbildung_general(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract continuing education with support for all education types"""
    weiterbildung = {
        # Vocational education
        "kurse": "",
        "zusatzlehre": [],
        "berufspruefung": [],
        "hoehere_fachpruefung": "",
        "hoehere_fachschule": "",
        "fachhochschule": "",

        # Academic education - generalized
        "bachelor": "",
        "master": "",
        "doktorat": "",
        "nachdiplomstufe": "",
        "weiterbildungsstudiengaenge": "",

        # General fields
        "allgemeine_weiterbildung": [],

        # Career progression and metadata
        "career_progression": [],
        "bildungstyp": "unknown"
    }

    anchor_element = soup.find(id="anchor4")
    if not anchor_element:
        return weiterbildung

    toggle_box = anchor_element.find_parent("div", class_="toggleBox")
    if not toggle_box:
        return weiterbildung

    box_content = toggle_box.find("div", class_="boxContent")
    if not box_content:
        return weiterbildung

    current_section = None

    # Detect education type by looking at headings
    all_headings = [h.get_text().lower() for h in box_content.find_all(["h3"])]

    # Academic indicators
    academic_indicators = ["universität", "master", "bachelor", "doktorat", "eth", "uni", "hochschule", "studium"]
    # Vocational indicators  
    vocational_indicators = ["berufsprüfung", "zusatzlehre", "kurse", "bp", "hfp", "hf"]

    if any(indicator in " ".join(all_headings) for indicator in academic_indicators):
        weiterbildung["bildungstyp"] = "academic"
    elif any(indicator in " ".join(all_headings) for indicator in vocational_indicators):
        weiterbildung["bildungstyp"] = "vocational"

    for element in box_content.find_all(["h3", "p", "ul", "li"]):
        if element.name == "h3":
            section_title = normalize_text(element.get_text()).lower()

            # Vocational education sections
            if "kurse" in section_title:
                current_section = "kurse"
            elif "zusatzlehre" in section_title:
                current_section = "zusatzlehre"
            elif "berufsprüfung" in section_title or "bp" in section_title:
                current_section = "berufspruefung"
            elif "höhere fachprüfung" in section_title or "hfp" in section_title:
                current_section = "hoehere_fachpruefung"
            elif "höhere fachschule" in section_title or ("hf" in section_title and "fachschule" in section_title):
                current_section = "hoehere_fachschule"
            elif "fachhochschule" in section_title or ("fh" in section_title and not "hf" in section_title):
                current_section = "fachhochschule"

            # Academic education sections - more general
            elif "bachelor" in section_title:
                current_section = "bachelor"
            elif "master" in section_title and "universität" in section_title:
                current_section = "master"
            elif "master" in section_title:
                current_section = "master"
            elif "doktorat" in section_title or "dr." in section_title or "promotion" in section_title:
                current_section = "doktorat"
            elif "nachdiplomstufe" in section_title or "nachdiplom" in section_title:
                current_section = "nachdiplomstufe"
            elif "weiterbildungsstudiengänge" in section_title or "weiterbildungsstudium" in section_title:
                current_section = "weiterbildungsstudiengaenge"
            else:
                # Catch-all for other continuing education
                current_section = "allgemeine_weiterbildung"

        elif element.name == "p" and current_section:
            text = normalize_text(element.get_text())
            if text:
                if current_section in [
                    "kurse", "hoehere_fachpruefung", "hoehere_fachschule", "fachhochschule",
                    "bachelor", "master", "doktorat", "nachdiplomstufe", "weiterbildungsstudiengaenge"
                ]:
                    weiterbildung[current_section] = text
                elif current_section == "zusatzlehre":
                    # Extract job titles for vocational paths
                    job_patterns = re.findall(r"([A-ZÄÖÜ][a-zäöüß/\-]+(?:/\-?(?:frau|in|mann))?\s+EF[ZA])(?![\w])", text)
                    for job in job_patterns:
                        clean_job = normalize_text(job)
                        if clean_job not in weiterbildung["zusatzlehre"]:
                            weiterbildung["zusatzlehre"].append(clean_job)
                elif current_section == "allgemeine_weiterbildung":
                    weiterbildung["allgemeine_weiterbildung"].append(text)

        elif element.name == "ul" and current_section == "berufspruefung":
            for li in element.find_all("li", recursive=False):
                item_text = normalize_text(li.get_text())
                if item_text:
                    weiterbildung["berufspruefung"].append(item_text)

    # Create structured career progression based on education type
    levels = []

    if weiterbildung["bildungstyp"] == "academic":
        level_counter = 1
        if weiterbildung["bachelor"]:
            levels.append({
                "level": level_counter, 
                "type": "Bachelor-Studium", 
                "description": weiterbildung["bachelor"]
            })
            level_counter += 1
        if weiterbildung["master"]:
            levels.append({
                "level": level_counter, 
                "type": "Master-Studium", 
                "description": weiterbildung["master"]
            })
            level_counter += 1
        if weiterbildung["doktorat"]:
            levels.append({
                "level": level_counter, 
                "type": "Doktorat/Promotion", 
                "description": weiterbildung["doktorat"]
            })
            level_counter += 1
        if weiterbildung["nachdiplomstufe"]:
            levels.append({
                "level": level_counter, 
                "type": "Nachdiplomstufe", 
                "description": weiterbildung["nachdiplomstufe"]
            })
            level_counter += 1
        if weiterbildung["weiterbildungsstudiengaenge"]:
            levels.append({
                "level": level_counter, 
                "type": "Weiterbildungsstudiengänge", 
                "description": weiterbildung["weiterbildungsstudiengaenge"]
            })
    else:
        # Vocational career path
        level_counter = 1
        if weiterbildung["zusatzlehre"]:
            levels.append({"level": level_counter, "type": "Zusatzlehre", "options": weiterbildung["zusatzlehre"]})
            level_counter += 1
        if weiterbildung["berufspruefung"]:
            levels.append({"level": level_counter, "type": "Berufsprüfung (BP)", "options": weiterbildung["berufspruefung"]})
            level_counter += 1
        if weiterbildung["hoehere_fachpruefung"]:
            levels.append({"level": level_counter, "type": "Höhere Fachprüfung (HFP)", "description": weiterbildung["hoehere_fachpruefung"]})
            level_counter += 1
        if weiterbildung["hoehere_fachschule"]:
            levels.append({"level": level_counter, "type": "Höhere Fachschule (HF)", "description": weiterbildung["hoehere_fachschule"]})
            level_counter += 1
        if weiterbildung["fachhochschule"]:
            levels.append({"level": level_counter, "type": "Fachhochschule (FH)", "description": weiterbildung["fachhochschule"]})

    weiterbildung["career_progression"] = levels

    return weiterbildung


def extract_berufsverhaeltnisse(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract career conditions with structured information"""
    anchor_element = soup.find(id="anchor5")
    if not anchor_element:
        return {"text": "", "arbeitsumgebung": [], "karrierechancen": ""}

    toggle_box = anchor_element.find_parent("div", class_="toggleBox")
    if not toggle_box:
        return {"text": "", "arbeitsumgebung": [], "karrierechancen": ""}

    box_content = toggle_box.find("div", class_="boxContent")
    if not box_content:
        return {"text": "", "arbeitsumgebung": [], "karrierechancen": ""}

    full_text = normalize_text(box_content.get_text())

    sentences = re.split(r'[.!?]+', full_text)

    arbeitsumgebung = []
    karrierechancen = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        if any(keyword in sentence.lower() for keyword in 
               ["arbeiten", "baustellen", "gerüsten", "schutzausrüstung", "team", "betrieben", "schulen", "forschung", "büro"]):
            arbeitsumgebung.append(sentence)

        elif any(keyword in sentence.lower() for keyword in 
                ["berufserfahrung", "positionen", "übernehmen", "teamleiterin", "baustellenleiter", "karriere", "aufstieg"]):
            karrierechancen = sentence

    return {
        "text": full_text,
        "arbeitsumgebung": arbeitsumgebung,
        "karrierechancen": karrierechancen
    }


def extract_weitere_informationen(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract additional information with enhanced address parsing"""
    weitere_info = {
        "adressen": [],
        "verwandte_berufe": [],
        "externe_links": []
    }

    anchor_element = soup.find(id="anchor7")
    if anchor_element:
        toggle_box = anchor_element.find_parent("div", class_="toggleBox")
        if toggle_box:
            box_content = toggle_box.find("div", class_="boxContent")
            if box_content:
                for p in box_content.find_all("p"):
                    strong = p.find("strong")
                    if strong:
                        full_text = normalize_text(p.get_text())
                        name = normalize_text(strong.get_text())

                        address_info = {"name": name}

                        phone_match = re.search(r"Tel\.?:?\s*([+\d\s]+)", full_text)
                        if phone_match:
                            address_info["telefon"] = phone_match.group(1).strip()

                        url_match = re.search(r"URL:\s*(https?://[^\s]+)", full_text)
                        if url_match:
                            address_info["website"] = url_match.group(1)

                        email_match = re.search(r"E-Mail:\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", full_text)
                        if email_match:
                            address_info["email"] = email_match.group(1)

                        lines = full_text.split('\n')
                        for line in lines:
                            line = line.strip()
                            if re.match(r".*[A-Za-z].*\d+.*", line) and "Tel" not in line and "URL" not in line:
                                address_info["adresse"] = line
                                break

                        address_info["volltext"] = full_text
                        weitere_info["adressen"].append(address_info)

    sidebar = soup.find("div", id="sidebar")
    if sidebar:
        for toggle_box in sidebar.find_all("div", class_="toggleBox"):
            box_title = toggle_box.find(["p", "div"], class_="boxTitle")
            if box_title and "verwandte berufe" in box_title.get_text().lower():
                box_content = toggle_box.find("div", class_="boxContent")
                if box_content:
                    for link in box_content.find_all("a", href=True):
                        href = link.get("href")
                        text = normalize_text(link.get_text())
                        if href and text and "id=" in href:
                            job_id = None
                            id_match = re.search(r"id=(\d+)", href)
                            if id_match:
                                job_id = id_match.group(1)

                            weitere_info["verwandte_berufe"].append({
                                "title": text,
                                "url": href,
                                "job_id": job_id
                            })
                break

    return weitere_info


def parse_detail_page_optimized(html: str, url: str) -> Dict[str, Any]:
    """Parse detail page with optimized comprehensive data extraction"""
    soup = BeautifulSoup(html, "html.parser")

    title, description = extract_title_and_description(soup)
    categories = extract_categories(soup)
    apprenticeship_info = extract_apprenticeship_info(soup)
    taetigkeiten = extract_taetigkeiten(soup)
    ausbildung = extract_ausbildung(soup)
    voraussetzungen = extract_voraussetzungen(soup)
    weiterbildung = extract_weiterbildung_general(soup)
    berufsverhaeltnisse = extract_berufsverhaeltnisse(soup)
    weitere_info = extract_weitere_informationen(soup)

    result = {
        "url": url,
        "job_id": get_job_id_from_url(url),
        "title": title,
        "description": description,
        "categories": categories,
        "apprenticeship_info": apprenticeship_info,
        "taetigkeiten": taetigkeiten,
        "ausbildung": ausbildung,
        "voraussetzungen": voraussetzungen,
        "weiterbildung": weiterbildung,
        "berufsverhaeltnisse": berufsverhaeltnisse,
        "weitere_informationen": weitere_info,

        "data_completeness": {
            "has_taetigkeiten": len(taetigkeiten.get("kategorien", {})) > 0,
            "has_ausbildung": bool(ausbildung.get("dauer")) or bool(ausbildung.get("grundlage")),
            "has_voraussetzungen": len(voraussetzungen.get("anforderungen", [])) > 0 or len(voraussetzungen.get("vorbildung", [])) > 0,
            "has_weiterbildung": len(weiterbildung.get("career_progression", [])) > 0,
            "has_berufsverhaeltnisse": bool(berufsverhaeltnisse.get("text")),
            "completeness_score": 0
        },

        "extraction_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "extraction_version": "optimized_v3.0_general_education"
    }

    completeness_fields = result["data_completeness"]
    total_fields = len([k for k in completeness_fields.keys() if k.startswith("has_")])
    complete_fields = sum(1 for k, v in completeness_fields.items() if k.startswith("has_") and v)
    result["data_completeness"]["completeness_score"] = round(complete_fields / total_fields, 2)

    return result


def get_job_id_from_url(url: str) -> Optional[str]:
    try:
        q = parse_qs(urlparse(url).query)
        values = q.get("id")
        return values[0] if values else None
    except Exception:
        return None


def save_job_to_mongodb(doc: Dict[str, Any]) -> bool:
    """Save job data to MongoDB using .env configuration"""
    try:
        config = get_mongodb_config()

        pymongo = __import__("pymongo")
        MongoClient = getattr(pymongo, "MongoClient")
        ASCENDING = getattr(pymongo, "ASCENDING")

        client = MongoClient(config["uri"])
        db = client[config["database"]]
        collection = db[config["collection"]]

        try:
            collection.create_index([("url", ASCENDING)], unique=True)
            collection.create_index([("job_id", ASCENDING)], unique=False)
            collection.create_index([("title", ASCENDING)], unique=False)
            collection.create_index([("categories.berufsfelder", ASCENDING)], unique=False)
        except Exception:
            pass

        result = collection.update_one(
            {"url": doc["url"]}, 
            {"$set": doc}, 
            upsert=True
        )

        if result.upserted_id:
            action = "inserted"
        elif result.modified_count > 0:
            action = "updated"
        else:
            action = "no_change"

        completeness = doc['data_completeness']['completeness_score']
        education_type = doc['weiterbildung']['bildungstyp']
        logging.info(f"MongoDB {action}: {doc['title']} (ID: {doc['job_id']}, Type: {education_type}, Completeness: {completeness*100}%)")

        client.close()
        return True

    except ImportError:
        logging.error("pymongo not installed. Run: pip install pymongo python-dotenv")
        return False
    except Exception as e:
        logging.error(f"MongoDB error: {e}")
        return False


def test_single_job_mongodb(url: str = "https://www.berufsberatung.ch/dyn/show/1900?lang=de&idx=10000&id=11644") -> None:
    """Test extraction and save to MongoDB using .env configuration"""
    if not test_mongodb_connection():
        logging.error("MongoDB connection failed. Scraping aborted.")
        return

    html = http_get(url)
    if not html:
        logging.error("Failed to fetch HTML")
        return

    doc = parse_detail_page_optimized(html, url)

    logging.info(f"Extracted: {doc['title']} (ID: {doc['job_id']}, Type: {doc['weiterbildung']['bildungstyp']}, Completeness: {doc['data_completeness']['completeness_score']*100}%)")

    success = save_job_to_mongodb(doc)

    if success:
        logging.info(f"Successfully processed: {doc['title']}")
    else:
        logging.error("Failed to save to MongoDB")


def extract_detail_links(overview_html: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(overview_html, "html.parser")
    links: List[str] = []
    for a in soup.select("a[href]"):
        href = a.get("href", "").strip()
        if not href:
            continue
        if DETAIL_PATH_HINT in href and "id=" in href:
            abs_url = urljoin(base_url, href)
            links.append(abs_url)

    seen = set()
    unique: List[str] = []
    for u in links:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    return unique


def crawl_multiple_jobs_mongodb(limit: int = 5) -> Tuple[int, int]:
    """Crawl multiple jobs and save to MongoDB using .env configuration"""
    if not test_mongodb_connection():
        logging.error("MongoDB connection failed. Crawling aborted.")
        return 0, 0

    html = http_get(OVERVIEW_URL)
    if html is None:
        logging.error("Could not load overview page")
        return 0, 0

    detail_links = extract_detail_links(html, OVERVIEW_URL)
    detail_links = detail_links[:limit]

    logging.info(f"Found {len(detail_links)} job URLs, processing {len(detail_links)} jobs")

    processed = 0
    errors = 0
    academic_jobs = 0
    vocational_jobs = 0

    for idx, link in enumerate(detail_links, start=1):
        logging.info(f"Processing ({idx}/{len(detail_links)}): {link}")
        sleep_with_jitter()

        page_html = http_get(link)
        if page_html is None:
            logging.warning(f"Could not load HTML: {link}")
            errors += 1
            continue

        try:
            doc = parse_detail_page_optimized(page_html, link)
            success = save_job_to_mongodb(doc)
            if success:
                processed += 1
                if doc['weiterbildung']['bildungstyp'] == 'academic':
                    academic_jobs += 1
                elif doc['weiterbildung']['bildungstyp'] == 'vocational':
                    vocational_jobs += 1
            else:
                errors += 1

        except Exception as exc:
            logging.error(f"Error processing {link}: {exc}")
            errors += 1

    logging.info(f"Crawling completed: {processed} successful ({academic_jobs} academic, {vocational_jobs} vocational, {processed - academic_jobs - vocational_jobs} other), {errors} errors")

    return processed, errors


def show_env_example() -> None:
    """Show example .env file configuration"""
    print("Example .env file:")
    print("MONGODB_URI=mongodb://localhost:27017")
    print("MONGODB_DB=ds_project")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if not os.path.exists(".env"):
        logging.error(".env file not found!")
        show_env_example()
        return

    # Test single job first
    test_single_job_mongodb("https://www.berufsberatung.ch/dyn/show/1900?lang=de&idx=10000&id=11644")

    # Ask if user wants to crawl more jobs
    try:
        response = input("Do you want to crawl more jobs? (y/n): ").lower().strip()

        if response.startswith('y'):
            limit = 10
            logging.info(f"Crawling {limit} additional jobs...")
            processed, errors = crawl_multiple_jobs_mongodb(limit)
        else:
            logging.info("Single test completed.")
    except KeyboardInterrupt:
        logging.info("Goodbye!")


if __name__ == "__main__":
    main()
