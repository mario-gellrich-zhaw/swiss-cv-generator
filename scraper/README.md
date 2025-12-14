# DS_project

## Scraper für berufsberatung.ch

Dieser einfache Python-Scraper liest die Seite `https://www.berufsberatung.ch/dyn/show/1893`, extrahiert Seitentitel, Meta-Description sowie alle verlinkten Texte/URLs und speichert die Ergebnisse als JSON und CSV.

### Voraussetzungen
- Python 3.9+

### Installation
```bash
# Von der Projektwurzel aus (swiss-cv-generator/)
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Nutzung
```bash
python job_scraper.py
```

### Hinweise
- Der Scraper nutzt `requests` mit Browser-ähnlichen Headern und `BeautifulSoup` zur HTML-Analyse.
- Bitte respektiere die Nutzungsbedingungen der Website und setze das Tool verantwortungsvoll ein.

## MongoDB-Integration

### Lokale MongoDB mit Docker starten
```bash
docker compose up -d
```

### Umgebungsvariablen setzen
Erstelle eine `.env` Datei im scraper Ordner basierend auf `.env.example`:
```bash
cp .env.example .env
# Dann .env bearbeiten und eigene MongoDB-Credentials eintragen
```

Beispiel Inhalt:
```bash
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=CV_DATA
```

### Scraper ausführen und in MongoDB speichern
```bash
python job_scraper.py
```