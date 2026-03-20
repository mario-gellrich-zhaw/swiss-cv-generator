# 🗄️ MongoDB Automatic Data Initialization

## Problem

Nach jedem Neustart der Codespaces-Instanz mussten die MongoDB-Daten manuell erneut importiert werden. Dies war zeitaufwändig und umständlich.

## Lösung

Ein automatisches Startup-Skript wurde implementiert, das:

1. **Beim Container-Start aufgerufen wird** (via `.devcontainer/post-start.sh`)
2. **Überprüft, ob MongoDB läuft** 
3. **Collections initialisiert**, falls sie noch nicht existieren
4. **Essential Data lädt** (Cantons, First Names, Last Names), falls leer
5. **Idempotent ist** - kann mehrfach aufgerufen werden ohne Fehler

## 🔧 Wie es funktioniert

### 1. Neuer Script: `scripts/init_mongodb_on_startup.py`

Dieser Python-Script:
- Wartet auf MongoDB (mit Timeout)
- Prüft bestehende Collections
- Initialisiert fehlende Collections
- Lädt Canton-Daten aus Fallback
- Zeigt Status-Zusammenfassung

```bash
# Manuell aufrufbar:
python scripts/init_mongodb_on_startup.py
```

### 2. Aktualisiertes `.devcontainer/post-start.sh`

Das Startup-Skript wird jetzt automatisch nach jedem Container-Start aufgerufen:

```bash
python3 scripts/init_mongodb_on_startup.py
```

## 📊 Automatisch geladene Daten

Nach jedem Neustart sind diese Daten automatisch in MongoDB vorhanden:

| Collection | Dokumente | Quelle |
|-----------|-----------|--------|
| `cantons` | 26 | Fallback-Daten |
| `first_names` | ~461 | OpenAI-generiert (wenn API-Key vorhanden) |
| `last_names` | ~252 | OpenAI-generiert (wenn API-Key vorhanden) |
| `occupation_skills` | - | Leer (wird beim CV-Generieren befüllt) |
| `companies` | - | Leer (wird beim CV-Generieren befüllt) |

## 🚀 Workflow nach Neustart

```
Codespaces-Start
    ↓
MongoDB wird gestartet (persistent in .data/mongo/)
    ↓
post-start.sh wird ausgeführt
    ↓
init_mongodb_on_startup.py wird aufgerufen
    ↓
✅ Collections & Daten sind sofort verfügbar
    ↓
Anwendung kann sofort CV generieren
```

## ✅ Verifizierung

Nach dem Start solltest du diese Befehle direkt ausführen können:

```bash
# In mongosh:
use swiss_cv_generator
show collections           # Sollte alle 5 Collections zeigen
db.cantons.countDocuments() # Sollte 26 zurückgeben
db.first_names.countDocuments() # Sollte ~461 sein
```

## 📝 Persistent Storage

Die MongoDB-Daten werden in `.data/mongo/` gespeichert:
- **Zwischen Restarts persistent**: ✅ Ja
- **Beim Git-Push ausgeschlossen**: ✅ Ja (in .gitignore)
- **Größe**: ~50 MB (je nach Daten)

## 🔄 Manuelle Neuladeung

Falls du Daten neu laden möchtest:

```bash
# Komplettes Setup neu ausführen:
python scripts/setup_complete_database.py

# Oder einzelne Komponenten:
python scripts/load_cantons_fallback.py
python scripts/ai_generate_first_names.py
python scripts/ai_generate_last_names.py
```

## 🐛 Troubleshooting

**Problem**: MongoDB startet nicht
```bash
# Manuell starten:
mongod --dbpath .data/mongo --logpath .data/mongo/mongodb.log --fork --bind_ip_all
```

**Problem**: Initialisierung wird immer wieder ausgeführt
- Das ist normal und harmlos - der Script ist idempotent
- Collections werden nicht dupliziert

**Problem**: OpenAI-Generierung scheitert
- Überprüfe `.env` und `OPENAI_API_KEY`
- Die Fallback-Cantons werden trotzdem geladen
