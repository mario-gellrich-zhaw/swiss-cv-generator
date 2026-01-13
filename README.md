# Swiss CV Generator

A comprehensive system for generating realistic, demographically authentic Swiss CVs with structured data from official sources and web scraping.

## Overview

The Swiss CV Generator produces high-quality curriculum vitae documents based on real Swiss demographic distributions, occupational data, and industry standards. The system combines data from the Swiss Federal Statistical Office (BFS) and scraped occupational information from berufsberatung.ch to create authentic CV profiles.

## Quick Start

### Option 1: GitHub Codespaces (Recommended)

The easiest way to get started is using GitHub Codespaces:

1. **Open in Codespaces:**
   - Click the green "Code" button on GitHub
   - Select "Codespaces" tab
   - Click "Create codespace on main"
   - Wait for the container to build (5-7 minutes)

2. **MongoDB Extension Setup (Important!):**
   During startup, VS Code will show a MongoDB popup asking for a connection string.
   - **Enter:** `mongodb://localhost:27017`
   - This allows the MongoDB extension to connect to the local database

3. **Automatic Setup:**
   The container automatically:
   - ✅ Installs all dependencies (Python 3.11, MongoDB, etc.)
   - ✅ Starts MongoDB service
   - ✅ Imports CV_DATA from JSON file (~1,851 occupations)
   - ✅ Creates `.env` configuration file
   - ✅ **Initializes complete database** (demographics, cantons, etc.)
   - ✅ Tests database connection

4. **Optional: Add OpenAI API Key**
   If the automatic setup shows warnings about missing names/companies:
   ```bash
   # Edit .env and add your OpenAI API key
   nano .env
   # Add: OPENAI_API_KEY=sk-...
   
   # Re-run database setup
   python scripts/setup_complete_database.py
    # If canton/name generation failed earlier, adding the key and rerunning fixes it
   
   # Or use fallback for cantons (no API key needed):
   python scripts/load_cantons_fallback.py
   ```

5. **Generate CVs:**
   ```bash
   python -m src.cli.main generate \
     --count 10 \
     --language de \
     --format pdf \
     --output-dir output/my_cvs \
     --verbose
   ```

**Note:** The Codespaces setup is fully automated! After the container builds, everything is ready to generate CVs. The setup script runs automatically and includes:
- MongoDB installation and startup
- Python dependencies installation
- CV_DATA database import
- Complete database initialization (cantons, demographics, etc.)
- Environment configuration

### Option 2: Local Setup

Generate 10 CVs in German with random professional designs:

```bash
# 1. Clone and setup
git clone <repository-url>
cd swiss-cv-generator
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. Configure MongoDB connection
cp .env.example .env
# Edit .env with your MongoDB credentials

# 3. Import CV_DATA database (required first step!)
# Option A: Import from JSON file (fast, recommended)
python scripts/import_cv_data.py

# Option B: Or run scraper to populate CV_DATA database
# cd scraper && python job_scraper.py && cd ..

# 4. Setup database (one-time)
python scripts/setup_complete_database.py

# 5. Generate CVs
python -m src.cli.main generate \
  --count 10 \
  --language de \
  --format pdf \
  --output-dir output/my_cvs \
  --verbose
```

Output: 10 professional CVs with random designs (classic, modern, minimal, timeline) in `output/my_cvs/de/all/`

**Important:** The CV_DATA database must be populated before CV generation can work. You can either:
- Import from the included JSON file: `python scripts/import_cv_data.py` (fast, recommended)
- Or run the scraper: `cd scraper && python job_scraper.py` (takes 25-45 minutes)

For detailed setup and generation options, see [Installation](#installation) and [CV Generation](#cv-generation) sections below.

## Architecture

### Project Structure

```
swiss-cv-generator/
├── src/                          # Core application code
│   ├── cli/                      # Command-line interface
│   ├── database/                 # MongoDB integration and queries
│   ├── generation/               # CV generation logic
│   ├── export/                   # PDF, JSON, DOCX exporters
│   ├── data/                     # Data models and loaders
│   ├── data_loaders/             # BFS and web scraping utilities
│   └── config.py                 # Configuration management
├── scraper/                      # Standalone web scraper for berufsberatung.ch
├── scripts/                      # Setup and utility scripts
├── templates/                    # CV templates (HTML/CSS)
├── data/                         # Demographic data and resources
│   ├── source/                   # Original source files
│   ├── processed/                # Processed datasets
│   ├── portraits/                # Profile images by age/gender
│   ├── official/                 # Official BFS data
│   └── schemas/                  # JSON schemas
├── tests/                        # Test suite
└── output/                       # Generated CVs (PDF/JSON/DOCX)
```

### Technology Stack

**Core Framework:**
- Python 3.9+
- Pydantic for data validation
- Click/Typer for CLI
- Rich for terminal UI

**Database:**
- MongoDB (dual database architecture)
  - Source DB (CV_DATA): Read-only scraped data
  - Target DB (swiss_cv_generator): Generated CVs and metadata

**Export:**
- ReportLab: Primary PDF generation
- WeasyPrint: Alternative HTML-to-PDF engine
- python-docx: DOCX export
- Pillow: Image processing

**AI Integration:**
- OpenAI API (GPT-3.5/GPT-4)
- Summary generation
- Skill extraction
- Responsibility text generation

**Web Scraping:**
- Requests + BeautifulSoup4
- Rate limiting and retry logic
- Structured data extraction

## Data Sources

### 1. Federal Statistical Office (BFS)

**Demographic Data** (`data/source/Bevölkerungsdaten.json`):
- Population structure by age and gender (ca. 2024)
- Total population: ~9.1 million
- Working age population (18-65): ~5.2 million

**Age Groups:**
- 18-25 years: 7.6% (693,000 persons)
- 26-40 years: 18.5% (1,685,000 persons)
- 41-65 years: 31.0% (2,800,000 persons)

**Industry Distribution** (`data/source/Branchenverteilung.json`):
- Wirtschaft/Verwaltung: 18.0%
- Gesundheit: 10.2%
- Bildung/Soziales: 7.7%
- Verkehr/Logistik: 5.8%
- Others distributed across sectors

### 2. Occupational Data (berufsberatung.ch)

**Source:** Web scraper in `/scraper/` directory

**Data Collection:**
- 1851 occupations and training programs
- Detailed job descriptions
- Educational requirements (EFZ, EBA, Hochschule)
- Career progression paths
- Required skills and competencies
- Industry classifications

**Scraper Features:**
- Automatic extraction from berufsberatung.ch
- MongoDB integration
- Rate limiting and error handling
- Data quality validation
- Completeness scoring

### 3. Portrait Images

**Location:** `data/portraits/`

**Organization:**
- Male/Female categories
- Three age groups: 18-25, 26-40, 41-65
- 5 portraits per category (30 total)
- AI-generated professional headshots
- Prompts documented in `cv_portrait_prompts.md`

## System Requirements

### Prerequisites

**Required:**
- Python 3.9 or higher
- MongoDB 4.4+ (local or Atlas)
- 2GB RAM minimum
- Internet connection for initial setup

**Optional:**
- OpenAI API key (for AI-generated content)
- Ghostscript (for PDF compression)

### Installation

#### GitHub Codespaces Setup

1. **Open Repository in Codespaces:**
   - Navigate to the repository on GitHub
   - Click the green "Code" button
   - Select "Codespaces" tab
   - Click "Create codespace on main"

2. **Wait for Container Build:**
   - The devcontainer automatically:
     - Installs Python 3.11
     - Installs all Python dependencies
     - Sets up MongoDB service
     - Configures VS Code extensions
     - Creates `.env` file with defaults
     - **Imports CV_DATA database from JSON file** (if available)

3. **Verify Setup:**
   ```bash
   # Test database connection
   python scripts/test_db_connection.py
   ```

4. **Continue with [Setup Process](#setup-process) below**

**Note:** The CV_DATA database is included as a JSON file (`data/CV_DATA.cv_berufsberatung.json`) and is automatically imported during Codespaces setup. You don't need to run the scraper!

#### Local Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd swiss-cv-generator
```

2. Create and activate virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up MongoDB:

**Option A: Local MongoDB with Docker**
```bash
docker compose -f scraper/docker-compose.yml up -d
```

**Option B: MongoDB Atlas**
- Create cluster at mongodb.com
- Get connection string
- Add to .env file

5. Configure environment variables:

Create `.env` file in project root (or copy from `.env.example`):
```bash
cp .env.example .env
```

Edit `.env` file:
```env
# MongoDB Configuration
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE_SOURCE=CV_DATA
MONGODB_DATABASE_TARGET=swiss_cv_generator
MONGODB_COLLECTION_OCCUPATIONS=cv_berufsberatung

# OpenAI Configuration (optional)
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL_MINI=gpt-3.5-turbo
OPENAI_MODEL_FULL=gpt-4

# Application Settings
DATA_DIR=data
LOG_LEVEL=INFO
AI_MAX_RETRIES=5
AI_RATE_LIMIT_DELAY=1.0
```

## Setup Process

### 1. Data Import (REQUIRED - Must Run First!)

**Option A: Import from JSON File (Recommended for Codespaces)**

The CV_DATA database is included as a JSON file in the repository (`data/CV_DATA.cv_berufsberatung.json`). This allows you to skip the scraper entirely:

```bash
# Import CV_DATA from JSON file
python scripts/import_cv_data.py
```

This will:
- Import all ~1851 occupations from the JSON file
- Create necessary indexes
- Takes only a few seconds

**Option B: Run the Scraper (Alternative)**

If you prefer to scrape fresh data from berufsberatung.ch:

```bash
# Configure MongoDB connection
cd scraper
cp .env.example .env
# Edit .env with your MongoDB credentials (URI and database name)

# Run the scraper
python job_scraper.py
cd ..
```

The scraper will:
- Extract all occupations from berufsberatung.ch (~1851 occupations)
- Parse structured data (education, skills, requirements)
- Store in MongoDB collection `cv_berufsberatung` in the CV_DATA database
- Apply rate limiting (0.8-1.6s between requests)
- Validate data completeness
- Takes approximately 25-45 minutes to complete

**Note:** Either import from JSON or run the scraper - you need one of these steps before proceeding to database initialization.

### 2. Database Initialization

After CV_DATA has been imported (from JSON) or populated (by scraper), run the complete setup script:

```bash
python scripts/setup_complete_database.py
```

This script orchestrates:
- Database connection validation
- Collection creation with indexes
- Demographic data import
- Occupation data migration from CV_DATA to swiss_cv_generator
- Name frequency data loading
- Company directory setup
- Portrait image organization
- Skill extraction from occupational data

Estimated time: 5-10 minutes (excluding AI-powered steps)

### 3. Verify Setup

Test database connectivity:
```bash
python scripts/test_db_connection.py
```

Expected output:
- Source DB collections: cv_berufsberatung
- Target DB collections: cantons, first_names, last_names, companies, demographic_config

## CV Generation

### Command Line Interface

**Basic Usage:**
```bash
python -m src.cli.main generate [OPTIONS]
```

**Common Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `--count, -n` | Number of CVs to generate | 1 |
| `--industry, -i` | Industry filter (technology, finance, healthcare, etc.) | None |
| `--language, -l` | Output language (de, fr, it) | de |
| `--career-level, -c` | Career level (junior, mid, senior, lead) | None |
| `--age-group, -a` | Age group (18-25, 26-40, 41-65) | None |
| `--with-portrait` | Include portrait image | True |
| `--format, -f` | Output format (pdf, docx, both) | pdf |
| `--output-dir, -o` | Output directory | output/cvs |
| `--validate-timeline` | Validate timeline consistency | True |
| `--validate-quality` | Run quality checks | True |
| `--min-quality-score` | Minimum quality score (0-100) | 80.0 |
| `--verbose, -v` | Detailed logging | False |

### Quick Start Examples

**Generate CVs with Random Designs:**

The system automatically selects from 4 different professional CV templates (classic, modern, minimal, timeline) for variety.

Generate 10 CVs in German with random designs (PDF only):
```bash
python -m src.cli.main generate \
  --count 10 \
  --language de \
  --format pdf \
  --output-dir output/my_cvs \
  --verbose
```

Generate 10 CVs in French with random designs:
```bash
python -m src.cli.main generate \
  --count 10 \
  --language fr \
  --format pdf \
  --output-dir output/cvs_fr
```

Generate 10 CVs in Italian with both PDF and JSON:
```bash
python -m src.cli.main generate \
  --count 10 \
  --language it \
  --format both \
  --output-dir output/cvs_it
```

**Industry-Specific Generation:**

Generate 10 technology CVs in German:
```bash
python -m src.cli.main generate \
  --count 10 \
  --industry technology \
  --language de \
  --output-dir output/tech_cvs
```

Generate 10 finance CVs in French:
```bash
python -m src.cli.main generate \
  --count 10 \
  --industry finance \
  --language fr \
  --output-dir output/finance_cvs
```

**Career Level Filtering:**

Generate 10 senior-level CVs:
```bash
python -m src.cli.main generate \
  --count 10 \
  --career-level senior \
  --language de \
  --output-dir output/senior_cvs
```

Generate 10 junior CVs with high quality threshold:
```bash
python -m src.cli.main generate \
  --count 10 \
  --career-level junior \
  --min-quality-score 90 \
  --output-dir output/junior_cvs
```

**Age Group Targeting:**

Generate 10 CVs for young professionals (26-40 years):
```bash
python -m src.cli.main generate \
  --count 10 \
  --age-group 26-40 \
  --language de \
  --output-dir output/young_professionals
```

**Complete Example with All Options:**
```bash
python -m src.cli.main generate \
  --count 10 \
  --industry technology \
  --language de \
  --career-level senior \
  --age-group 41-65 \
  --format pdf \
  --output-dir output/tech_senior_cvs \
  --validate-timeline \
  --validate-quality \
  --min-quality-score 85 \
  --verbose
```

### Output Structure

Generated CVs are organized by language and industry:

```
output/
└── my_cvs/
    └── de/
        └── all/  # or specific industry name
            ├── Müller_Anna_21324_20251214_120000.pdf
            ├── Meier_Hans_21325_20251214_120005.pdf
            └── ...
```

Each CV filename contains:
- Last name
- First name
- Job ID
- Timestamp (YYYYMMDD_HHMMSS)

### Available Templates

The system uses 4 different professional templates, randomly selected for each CV:

1. **Classic**: Traditional two-column layout with blue accent
2. **Modern**: Contemporary design with dark sidebar and green accent
3. **Minimal**: Clean, minimalist design
4. **Timeline**: Timeline-based layout

This ensures visual variety across generated CVs while maintaining professional standards.

### Programmatic Usage

```python
from src.generation.sampling import SamplingEngine
from src.generation.cv_assembler import generate_complete_cv
from src.cli.main import export_cv_pdf, export_cv_json

# Initialize sampling engine
engine = SamplingEngine()

# Sample persona with industry preference
persona = engine.sample_persona(preferred_industry='technology')

# Generate complete CV
cv_document, quality_report = generate_complete_cv(persona)

# Export to PDF
export_cv_pdf(cv_document, Path("output/cv.pdf"))

# Export to JSON
export_cv_json(cv_document, Path("output/cv.json"))
```

## Generation Process

### 1. Persona Sampling

The system samples demographic attributes using weighted distributions:

**Process:**
1. Select age group (weighted by population)
2. Determine gender (50/50 distribution)
3. Select canton (weighted by population)
4. Determine primary language based on canton
5. Sample occupation based on industry distribution
6. Generate name using language-specific frequency data
7. Select appropriate portrait image
8. Generate contact information

**Sampling Weights** (`data/sampling_weights.json`):
```json
{
  "age_groups": {
    "18-25": 7.6,
    "26-40": 18.5,
    "41-65": 31.0
  }
}
```

### 2. Education History Generation

**Components:**
- Mandatory education (Primarschule, Sekundarschule)
- Vocational training or university education
- Additional qualifications based on career level
- Realistic institutions and locations
- Chronologically consistent timelines

**Education Types:**
- EFZ (Eidgenössisches Fähigkeitszeugnis)
- EBA (Eidgenössisches Berufsattest)
- Fachhochschule (FH)
- Universität
- Höhere Fachschule (HF)

### 3. Job History Generation

**Timeline Construction:**
- Forward calculation from education completion
- Career progression (Junior → Mid → Senior → Lead)
- Realistic company selection by industry and canton
- Gap handling (parental leave, education, sabbaticals)
- AI-generated responsibilities per position

**Validation Rules:**
- No overlapping positions
- Gaps under 6 months: acceptable
- Gaps 6-12 months: filled with education/projects
- Gaps over 24 months: CV rejected and regenerated

### 4. Timeline Validation

**Checks:**
- Start dates before end dates
- No future dates
- Age consistency with work history
- Education-to-work transition logic
- Total experience matches career level

### 5. CV Assembly

**Components:**
- Personal information (name, age, contact)
- Professional summary (AI-generated or template)
- Work experience with detailed responsibilities
- Education history
- Skills (technical and soft skills)
- Languages (based on canton and background)
- Additional qualifications
- Hobbies and interests
- Portrait image

### 6. Quality Validation

**Scoring System (0-100):**

| Category | Weight | Criteria |
|----------|--------|----------|
| Completeness | 30% | All required fields present |
| Realism | 35% | Consistent timeline, valid companies, appropriate skills |
| Language Quality | 20% | Proper grammar, reasonable length |
| Achievements | 15% | Concrete responsibilities and accomplishments |

**Thresholds:**
- 90-100: Excellent
- 80-89: Good (default minimum)
- 70-79: Acceptable
- Below 70: Rejected and regenerated

### 7. Export

**PDF Export:**
- ReportLab rendering engine
- Swiss CV format (one page)
- Professional layout with sections
- Embedded portrait image
- Size: ~80-90 KB per CV

**JSON Export:**
- Complete structured data
- All persona attributes
- Work history details
- Education records
- Skills and qualifications
- Quality metrics

**DOCX Export:**
- Formatted document with headings
- Bulleted lists for responsibilities
- Compatible with Microsoft Word

**File Naming Convention:**
```
{LASTNAME}_{FIRSTNAME}_{JOB_ID}_{TIMESTAMP}.{pdf|json|docx}
```

## Database Schema

### Source Database: CV_DATA

**Collection: cv_berufsberatung**

Contains 1851 occupations with structure:
```json
{
  "id": "21324",
  "name_de": "Software Engineer",
  "name_fr": "Ingénieur logiciel",
  "name_it": "Ingegnere software",
  "berufsfeld": "Informatik",
  "branchen": "Informatik - Elektrotechnik",
  "industry": "technology",
  "bildungstyp": "Berufliche Grundbildung 3 Jahre",
  "swissdoc": "21324.1",
  "ausbildung": {
    "dauer": "3 Jahre",
    "inhalt": [...],
    "abschluss": "EFZ"
  },
  "taetigkeiten": {
    "kategorien": [...]
  },
  "voraussetzungen": {
    "anforderungen": [...],
    "kategorisierte_anforderungen": {
      "physische_anforderungen": [...],
      "fachliche_faehigkeiten": [...],
      "persoenliche_eigenschaften": [...]
    }
  },
  "weiterbildung": {
    "career_progression": [...]
  },
  "skills": [...],
  "activities": [...]
}
```

**Indexes:**
- `url` (unique)
- `job_id`
- `title`
- `categories.berufsfelder`

### Target Database: swiss_cv_generator

**Collection: cantons**
```json
{
  "code": "ZH",
  "name": "Zürich",
  "population": 1553423,
  "primary_language": "de"
}
```

**Collection: first_names**
```json
{
  "name": "Anna",
  "language": "de",
  "gender": "female",
  "frequency": 8500
}
```

**Collection: companies**
```json
{
  "name": "Swiss Tech Solutions AG",
  "canton": "ZH",
  "industry": "technology",
  "size_band": "50-249"
}
```

**Collection: demographic_config**
```json
{
  "config_type": "age_weights",
  "data": {
    "18-25": 7.6,
    "26-40": 18.5,
    "41-65": 31.0
  }
}
```

## Configuration

### Environment Variables

All configuration via `.env` file or environment variables:

**MongoDB:**
- `MONGODB_URI`: Connection string
- `MONGODB_DATABASE_SOURCE`: Source database name
- `MONGODB_DATABASE_TARGET`: Target database name
- `MONGODB_COLLECTION_OCCUPATIONS`: Occupations collection name

**OpenAI:**
- `OPENAI_API_KEY`: API key for GPT models
- `OPENAI_MODEL_MINI`: Model for simple tasks (gpt-3.5-turbo)
- `OPENAI_MODEL_FULL`: Model for complex tasks (gpt-4)

**Application:**
- `DATA_DIR`: Data directory path
- `LOG_LEVEL`: Logging verbosity (DEBUG, INFO, WARNING, ERROR)
- `AI_MAX_RETRIES`: Maximum retry attempts for AI calls
- `AI_RATE_LIMIT_DELAY`: Delay between AI requests (seconds)
- `AI_TEMPERATURE_CREATIVE`: Temperature for creative text (0.0-1.0)
- `AI_TEMPERATURE_FACTUAL`: Temperature for factual text (0.0-1.0)

### Configuration Management

Configuration handled by Pydantic Settings with priority:
1. Environment variables (highest)
2. `.env` file
3. Default values in `src/config.py`

Type validation and conversion automatic via Pydantic.

## Scripts Reference

### Setup Scripts

**setup_complete_database.py**
- Orchestrates full database initialization
- Creates collections and indexes
- Imports demographic data
- Validates setup completion

**setup_demographic_sampling.py**
- Loads demographic weights into MongoDB
- Configures age, gender, canton distributions
- Imports industry percentages

**migrate_occupations_to_mongodb.py**
- Migrates occupation data to MongoDB
- Validates data structure
- Creates required indexes

### Data Processing Scripts

**process_occupations.py**
- Normalizes occupation data from source
- Extracts industry mappings
- Processes education requirements
- Outputs to `data/processed/occupations.json`

**extract_and_enhance_companies.py**
- Extracts company data from various sources
- Validates industry classifications
- Enhances with canton information

**organize_portrait_images.py**
- Organizes portrait images by age and gender
- Creates portrait index
- Validates image availability

### Name Generation Scripts

**ai_generate_first_names.py**
- Generates culturally appropriate first names
- Uses GPT for realistic Swiss names
- Outputs frequency-weighted lists per language

**ai_generate_last_names.py**
- Generates Swiss surnames
- Considers regional variations
- Outputs with frequency distributions

**validate_names.py**
- Validates name quality and authenticity
- Checks for duplicates
- Verifies frequency distributions

### CV Generation Scripts

**generate_cv_batch.py**
- Batch generation with progress tracking
- Quality validation and retry logic
- Configurable output formats

**generate_cv_parallel.py**
- Parallel processing using multiprocessing
- Significant performance improvement for large batches
- Automatic load balancing

### Utility Scripts

**test_db_connection.py**
- Tests MongoDB connectivity
- Validates database access
- Lists available collections

**analyze_cv_data_occupations.py**
- Analyzes occupation data quality
- Generates field mapping documentation
- Outputs to `data/cv_data_mapping.json`

## Templates

### PDF Templates

**Location:** `templates/pdf/`

**Available Languages:**
- `de.html`: German
- `fr.html`: French
- `it.html`: Italian

**Template Structure:**
- Jinja2 syntax for dynamic content
- Responsive design for PDF rendering
- Professional Swiss CV layout
- Section-based organization

**Customization:**
- Edit HTML templates directly
- Modify CSS in `templates/styles/cv.css`
- Add custom sections or fields
- Adjust spacing and fonts

### Styling

**Location:** `templates/styles/cv.css`

**Features:**
- Print-optimized styles
- Professional color scheme
- Consistent typography
- Section dividers and spacing

## Output Structure

Generated CVs organized by language and industry:

```
output/cvs/
├── de/
│   ├── technology/
│   │   ├── Meier_Anna_21324_20240101_120000.pdf
│   │   ├── Meier_Anna_21324_20240101_120000.json
│   │   └── ...
│   ├── finance/
│   └── healthcare/
├── fr/
└── it/
```

## Performance Considerations

### Single CV Generation
- Time: ~2-5 seconds (without AI)
- Time: ~5-10 seconds (with AI summaries)
- Memory: ~50-100 MB

### Batch Generation (100 CVs)
- Sequential: ~8-15 minutes
- Parallel (4 cores): ~3-5 minutes
- Memory: ~200-400 MB peak

### Database Performance
- Occupation lookup: <10ms with indexes
- Company sampling: <5ms
- Name generation: <1ms

### Optimization Tips
- Use parallel generation for batches >10
- Enable caching for repeated queries
- Disable AI generation for faster output
- Pre-load portrait images in memory

## Troubleshooting

### MongoDB Connection Issues

**Problem:** Cannot connect to MongoDB
**Solution:**
- Verify MongoDB is running: `docker ps` or check Atlas
- Check connection string in `.env`
- Ensure network connectivity
- Verify credentials

### Missing Data

**Problem:** No occupations found
**Solution:**
- Run scraper: `cd scraper && python job_scraper.py`
- Or run setup: `python scripts/setup_complete_database.py`
- Verify MongoDB collections exist

### Low Quality Scores

**Problem:** Generated CVs score below threshold
**Solution:**
- Lower `--min-quality-score` threshold
- Enable AI generation for better summaries
- Check occupation data completeness
- Verify timeline validation rules

### PDF Generation Errors

**Problem:** PDF export fails
**Solution:**
- Check ReportLab installation: `pip install reportlab`
- Verify template files exist in `templates/pdf/`
- Check portrait image availability
- Try alternative engine: WeasyPrint

### Timeline Validation Failures

**Problem:** Many CVs rejected for timeline issues
**Solution:**
- Review gap tolerance settings
- Check education duration calculations
- Verify career level progression logic
- Examine age group constraints

## Development

### Running Tests

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_data.py

# Run with coverage
pytest --cov=src tests/
```

### Code Quality

```bash
# Format code
black src/ scripts/ tests/

# Lint
pylint src/ scripts/

# Type checking
mypy src/
```

### Contributing

Guidelines for development:
- Follow PEP 8 style guide
- Add type hints to all functions
- Write unit tests for new features
- Update documentation for API changes
- Use meaningful commit messages

## Limitations

### Current Limitations

- Portrait images: Fixed set of 30 AI-generated images
- Companies: Limited company database, may use generic names
- Languages: German, French, Italian only (no English)
- Skills: Industry-based, not role-specific in all cases
- Timeline: Simplified gap handling, no complex career patterns
- AI dependency: Requires OpenAI API for highest quality

### Known Issues

- Some occupation descriptions may be verbose
- Company names occasionally generic
- Timeline gaps may require manual adjustment
- Portrait matching not perfect for all personas
- PDF rendering varies slightly by engine

## License

MIT License - See LICENSE file for details

## Support

For issues, questions, or contributions:
- Open an issue on GitHub
- Review existing documentation
- Check troubleshooting section
- Contact project maintainers

## Version History

**Current Version:** 0.1.0

### Recent Changes
- Initial release with core functionality
- MongoDB integration for data management
- Web scraper for berufsberatung.ch
- Multi-language support (de/fr/it)
- Quality validation system
- Parallel generation support
- PDF/JSON/DOCX export formats
