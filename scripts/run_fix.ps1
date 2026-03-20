# run_fix.ps1 (corrected)
Write-Output "Corrected run_fix started."

# Preflight
if (-not (Test-Path .\src)) {
    Write-Warning "src/ not found — ensure you're in the project root."
}

# Add pyproject to quiet pip editable deprecation
@"
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"
"@ | Out-File -Encoding utf8 -Force pyproject.toml
Write-Output "Wrote pyproject.toml"

# Fix escaped sequences in Python files under src/ (safe replaces)
Get-ChildItem -Path src -Recurse -Filter *.py | ForEach-Object {
    $file = $_.FullName
    try {
        $text = Get-Content -Raw -LiteralPath $file
        # Replace backslash-doublequote with plain double-quote
        $text = $text -replace '\\\"', '"'
        # Replace stray f\" -> f"
        $text = $text -replace 'f\"', 'f"'
        Set-Content -LiteralPath $file -Value $text -Encoding utf8
        Write-Output "Fixed escapes in: $file"
    } catch {
        Write-Warning "Failed to process $file : $_"
    }
}

# Ensure scripts folder and write fetch helper (if not present)
New-Item -ItemType Directory -Force -Path scripts | Out-Null

@"
# scripts\fetch_sfsodata.ps1
<#
Downloads BFS datasets into ./data. If auto-download fails, you'll be prompted
for a direct CSV/JSON URL. Run this script separately if you want to feed URLs manually.
#>
param([string]$OutputDir = "data")
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

function TryDownload($url, $outPath) {
    try {
        Write-Output "Attempting: $url -> $outPath"
        Invoke-WebRequest -Uri $url -OutFile $outPath -UseBasicParsing -ErrorAction Stop
        Write-Output "Saved: $outPath"
        return $true
    } catch {
        Write-Warning "Failed: $url (`$($_.Exception.Message)`)."
        return $false
    }
}

# Example candidate URLs (placeholders). Replace with direct CSV links if needed.
$demographicsCandidates = @(
    "https://www.bfs.admin.ch/bfsstatic/dam/assets/32208093/master",
    "https://www.bfs.admin.ch/dam/jcr:32208093-0cda-4f8b-b7f2-0e8d2f3b1a6e/canton_demographics.csv"
)
$demographicsOut = Join-Path $OutputDir "bfs_demographics_by_canton.csv"
$ok = $false
foreach ($u in $demographicsCandidates) {
    if (TryDownload $u $demographicsOut) { $ok = $true; break }
}
if (-not $ok) {
    $userUrl = Read-Host "Demographics CSV URL (paste direct CSV link or Enter to skip)"
    if (![string]::IsNullOrWhiteSpace($userUrl)) { TryDownload $userUrl $demographicsOut | Out-Null } else { Write-Warning "Skipping demographics." }
}

# Lastnames
$lastnamesCandidates = @(
    "https://www.bfs.admin.ch/bfsstatic/dam/assets/36062356/master",
    "https://www.bfs.admin.ch/dam/jcr:36062356-.../lastnames_by_canton.csv"
)
$lastnamesOut = Join-Path $OutputDir "bfs_lastnames_by_canton.csv"
$ok = $false
foreach ($u in $lastnamesCandidates) { if (TryDownload $u $lastnamesOut) { $ok = $true; break } }
if (-not $ok) {
    $userUrl = Read-Host "Lastnames CSV URL (paste direct CSV link or Enter to skip)"
    if (![string]::IsNullOrWhiteSpace($userUrl)) { TryDownload $userUrl $lastnamesOut | Out-Null } else { Write-Warning "Skipping lastnames." }
}

# Firstnames
$firstnamesCandidates = @(
    "https://www.bfs.admin.ch/bfsstatic/dam/assets/32208746/master",
    "https://www.bfs.admin.ch/dam/jcr:32208746-.../firstnames_by_year.csv"
)
$firstnamesOut = Join-Path $OutputDir "bfs_firstnames.csv"
$ok = $false
foreach ($u in $firstnamesCandidates) { if (TryDownload $u $firstnamesOut) { $ok = $true; break } }
if (-not $ok) {
    $userUrl = Read-Host "Firstnames CSV URL (paste direct CSV link or Enter to skip)"
    if (![string]::IsNullOrWhiteSpace($userUrl)) { TryDownload $userUrl $firstnamesOut | Out-Null } else { Write-Warning "Skipping first names." }
}

Write-Output "Fetch helper finished. Edit scripts\fetch_sfsodata.ps1 to add direct CSV links for non-interactive runs."
"@ | Out-File -Encoding utf8 -Force scripts\fetch_sfsodata.ps1

# Write name-frequency generator
@"
# scripts/generate_name_freqs.py
import argparse, csv, collections, os
def detect_columns(header):
    lower = [h.lower() for h in header]
    name_cols = [i for i,h in enumerate(lower) if 'name' in h or 'vorname' in h or 'vornamen' in h]
    freq_cols = [i for i,h in enumerate(lower) if 'freq' in h or 'anz' in h or 'count' in h or 'number' in h]
    return name_cols, freq_cols
def aggregate_names(input_csv, out_map):
    with open(input_csv, newline='', encoding='utf-8') as fh:
        reader = csv.reader(fh)
        header = next(reader, [])
        name_cols, freq_cols = detect_columns(header)
        for row in reader:
            if not row: continue
            name = row[name_cols[0]].strip() if name_cols else row[0].strip()
            freq = 1
            if freq_cols:
                try:
                    freq = int(row[freq_cols[0]])
                except:
                    freq = 1
            lang = 'de'
            for i,h in enumerate(header):
                if 'kant' in h.lower() or 'canton' in h.lower():
                    canton = row[i].strip()
                    if canton.upper().startswith('TI'): lang='it'
                    elif canton.upper().startswith('VD') or canton.upper().startswith('GE') or canton.upper().startswith('FR'): lang='fr'
                    break
            out_map[lang][name] += freq
def write_counter_to_csv(counter, path):
    with open(path, 'w', newline='', encoding='utf-8') as fh:
        writer = csv.writer(fh)
        writer.writerow(['name','frequency'])
        for name, freq in counter.most_common():
            writer.writerow([name, freq])
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--firstnames', required=False)
    parser.add_argument('--lastnames', required=False)
    parser.add_argument('--outdir', default='data')
    args = parser.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    names = {'de': collections.Counter(), 'fr': collections.Counter(), 'it': collections.Counter()}
    surnames = collections.Counter()
    if args.firstnames and os.path.exists(args.firstnames):
        aggregate_names(args.firstnames, names)
    if args.lastnames and os.path.exists(args.lastnames):
        with open(args.lastnames, newline='', encoding='utf-8') as fh:
            reader = csv.reader(fh)
            header = next(reader, [])
            name_cols, freq_cols = detect_columns(header)
            for row in reader:
                if not row: continue
                name = row[name_cols[0]].strip() if name_cols else row[0].strip()
                freq = 1
                if freq_cols:
                    try:
                        freq = int(row[freq_cols[0]])
                    except:
                        freq = 1
                surnames[name] += freq
    write_counter_to_csv(surnames, os.path.join(args.outdir, 'surnames.csv'))
    write_counter_to_csv(names['de'], os.path.join(args.outdir, 'names_de.csv'))
    write_counter_to_csv(names['fr'], os.path.join(args.outdir, 'names_fr.csv'))
    write_counter_to_csv(names['it'], os.path.join(args.outdir, 'names_it.csv'))
    print('Wrote name files to', args.outdir)
if __name__ == '__main__':
    main()
"@ | Out-File -Encoding utf8 -Force scripts\generate_name_freqs.py

# Overwrite sampling engine safely (keeps previously provided logic)
@"
# src/generation/sampling.py
import random, os, csv
from datetime import date
from src.data.loader import load_cantons_csv, load_companies_csv, load_occupations_json
from src.data.models import SwissPersona, Language
def weighted_choice(items, weights):
    total = sum(weights); r = random.random() * total; upto = 0
    for item, w in zip(items, weights):
        if upto + w >= r: return item
        upto += w
    return items[-1]
def load_name_csv(path):
    names, weights = [], []
    if not os.path.exists(path): return names, weights
    with open(path, newline='', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            nm = r.get('name') or r.get('Name') or r.get('vorname') or next(iter(r.values()))
            freq = r.get('frequency') or r.get('freq') or r.get('anzahl') or r.get('count') or '1'
            try: w = int(freq)
            except: w = 1
            names.append(nm); weights.append(w)
    return names, weights
class SamplingEngine:
    def __init__(self, data_dir='data'):
        self.cantons = load_cantons_csv(os.path.join(data_dir,'cantons.csv'))
        self.companies = load_companies_csv(os.path.join(data_dir,'companies.csv'))
        try: self.occupations = load_occupations_json(os.path.join(data_dir,'occupations.json'))
        except: self.occupations = []
        self.surnames, self.surname_weights = load_name_csv(os.path.join(data_dir,'surnames.csv'))
        self.names_de, self.names_de_weights = load_name_csv(os.path.join(data_dir,'names_de.csv'))
        self.names_fr, self.names_fr_weights = load_name_csv(os.path.join(data_dir,'names_fr.csv'))
        self.names_it, self.names_it_weights = load_name_csv(os.path.join(data_dir,'names_it.csv'))
    def sample_canton(self):
        weights = [c.population for c in self.cantons]; return weighted_choice(self.cantons, weights)
    def sample_language_for_canton(self, canton):
        probs = {canton.primary_language: 0.9}
        for l in ['de','fr','it']:
            if l != canton.primary_language: probs[l] = probs.get(l, 0.05)
        langs = list(probs.keys()); weights = list(probs.values()); return Language(weighted_choice(langs, weights))
    def sample_age(self, min_age=20, max_age=65): return random.randint(min_age, max_age)
    def age_to_experience(self, age, education_end_age=22, variance=2.0):
        base = max(0, age - education_end_age); var = int(random.gauss(0, variance)); return max(0, base + var)
    def career_level_from_experience(self, experience, industry):
        if experience < 3: return 'Junior'
        if experience < 7: return 'Mid'
        return 'Senior'
    def sample_name(self, language, gender=None):
        surname = weighted_choice(self.surnames, self.surname_weights) if self.surnames else random.choice(['Müller','Meier','Schmid','Bianchi'])
        if language == Language.de and self.names_de: first = weighted_choice(self.names_de, self.names_de_weights)
        elif language == Language.fr and self.names_fr: first = weighted_choice(self.names_fr, self.names_fr_weights)
        elif language == Language.it and self.names_it: first = weighted_choice(self.names_it, self.names_it_weights)
        else:
            pool = (self.names_de + self.names_fr + self.names_it); w = (self.names_de_weights + self.names_fr_weights + self.names_it_weights)
            first = weighted_choice(pool, w) if pool else random.choice(['Luca','Anna','Marco','Sophie'])
        return first, surname
    def sample_persona(self, preferred_canton=None, preferred_industry=None):
        canton = None
        if preferred_canton and preferred_canton != 'all': canton = next((c for c in self.cantons if c.code == preferred_canton), None)
        if not canton: canton = self.sample_canton()
        language = self.sample_language_for_canton(canton)
        age = self.sample_age(); exp = self.age_to_experience(age)
        industry = preferred_industry or (self.occupations[0].industry if self.occupations else 'technology')
        possible_companies = [c for c in self.companies if c.industry == industry and c.canton == canton.code]
        company = possible_companies[0].name if possible_companies else (self.companies[0].name if self.companies else 'Acme AG')
        first, surname = self.sample_name(language)
        full = f"{first} {surname}"
        persona = SwissPersona(
            first_name=first,
            last_name=surname,
            full_name=full,
            canton=canton.code,
            language=language,
            age=age,
            birth_year=date.today().year - age,
            gender=random.choice(['male','female','other']),
            experience_years=exp,
            industry=industry,
            current_title=f"{self.career_level_from_experience(exp, industry)} {industry.capitalize()}",
            career_history=[{'title': f"{self.career_level_from_experience(exp, industry)} {industry}", 'company': company, 'start_date': '2018-01', 'end_date': '2022-12', 'desc': 'Worked on projects.'}],
            email=f"{first.lower()}.{surname.lower()}@example.ch",
            phone=f"07{random.randint(60,99)}{random.randint(100000,999999)}",
            skills=['Problem solving', 'Software development'],
            summary=None,
            photo_path=None
        )
        return persona
"@ | Out-File -Encoding utf8 -Force src\generation\sampling.py

Write-Output "Wrote src/generation/sampling.py"

# 6) Install editable package
try {
    Write-Output "Installing package in editable mode..."
    & pip install -e .
    Write-Output "pip install completed."
} catch {
    Write-Warning "pip install failed: $_"
}

# 7) Run fetch script (interactive if required)
try {
    Write-Output "Running fetch script..."
    & .\scripts\fetch_sfsodata.ps1
    Write-Output "Fetch script completed."
} catch {
    Write-Warning "Fetch script execution failed: $_"
}

# 8) Generate normalized names if input files exist
try {
    Write-Output "Generating name-frequency CSVs (if input files present)..."
    $args = @()
    if (Test-Path "data\bfs_firstnames.csv") { $args += "--firstnames"; $args += "data\bfs_firstnames.csv" }
    if (Test-Path "data\bfs_lastnames_by_canton.csv") { $args += "--lastnames"; $args += "data\bfs_lastnames_by_canton.csv" }
    $args += "--outdir"; $args += "data"
    & python .\scripts\generate_name_freqs.py $args
    Write-Output "Name-frequency generation attempted."
} catch {
    Write-Warning "Name-frequency generation failed: $_"
}

# 9) Run pytest (show output)
try {
    Write-Output "Running pytest..."
    & pytest -q
} catch {
    Write-Warning "pytest failed or returned errors."
}

# 10) CLI smoke test
try {
    Write-Output "Running CLI smoke test..."
    & python -m src.cli.main generate --count 1 --output-dir sample_outputs
} catch {
    Write-Warning "CLI smoke test failed: $_"
}

Write-Output "run_fix.ps1 finished."
