# mhd-stats

Dlhodobý zber polôh a meškaní vozidiel MHD (Bratislava) do SQLite a jednoduché štatistiky
(meškania podľa linky / hodiny / dňa, počet vozidiel v prevádzke, úzke hrdlá).

Nezávislý projekt, nie je súčasťou Dopravného podniku Bratislava.

## Obsah

| Súbor | Účel |
|---|---|
| `collector.py` | zber dát do SQLite (GTFS-realtime alebo JSON API) |
| `stats.py` | štatistické prehľady z databázy |
| `mapping.example.json` | vzor mapovania polí pre JSON zdroj |
| `tests/selftest.py` | test bez internetu (falošný server) |
| `deploy/mhd-collector.service` | systemd služba pre Linux server |
| `Dockerfile`, `docker-compose.yml`, `.env.example` | beh v Dockeri |

---

# DETAILNÝ POSTUP

## Krok 1: Príprava počítača

Potrebujete **Python 3.9 alebo novší** a **git**.

- **Windows:** Python z python.org (pri inštalácii zaškrtnite *Add Python to PATH*), git z git-scm.com.
- **macOS:** `brew install python git`
- **Linux (Debian/Ubuntu):** `sudo apt install python3 python3-venv git`

Overenie: `python3 --version` (na Windows `python --version`) a `git --version`.

## Krok 2: Rozbalenie a inštalácia

```bash
unzip mhd-stats.zip          # Windows: pravé tlačidlo -> Extrahovať všetko
cd mhd-stats
python3 -m venv .venv
source .venv/bin/activate    # Windows (PowerShell): .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Overenie, že všetko funguje (nepotrebuje internet):

```bash
python tests/selftest.py     # výstup: OK: všetky testy prešli
```

## Krok 3: Zistenie zdroja dát

Skript potrebuje adresu, ktorá vracia aktuálne polohy vozidiel. Sú dve cesty.

**A) Oficiálny open data feed (odporúčané).** Skontrolujte portál otvorených dát
Bratislavy (opendata.bratislava.sk) a stránky Dopravného podniku Bratislava, či
publikujú GTFS-realtime (`vehicle positions`, `trip updates`). Je to stabilné a bezproblémové.

**B) Dáta, ktoré používa web `kdejemhd.sk`.**
1. Otvorte stránku v prehliadači (Chrome/Firefox) a stlačte **F12**.
2. Prejdite do záložky **Network** a vyberte filter **Fetch/XHR**.
3. Obnovte stránku (F5). Hľadajte požiadavku, ktorá sa opakuje každých pár sekúnd a vracia
   zoznam vozidiel (súradnice, číslo linky).
4. Kliknite na ňu, v záložke **Headers** skopírujte **Request URL**, v záložke **Response**
   uvidíte štruktúru JSON.
5. Pred dlhodobým zberom si overte podmienky používania a či autor webu nezverejňuje
   priamo API alebo kód (jeho GitHub je odkazovaný v pätičke stránky). Ak existuje
   oficiálny zdroj, použite ten, nie web scraping.

## Krok 4: Nastavenie mapovania (iba pre JSON zdroj)

```bash
cp mapping.example.json mapping.json
```

Otvorte `mapping.json` a upravte podľa skutočnej odpovede:

- `list_path` je bodková cesta k poľu vozidiel. Ak je odpoveď priamo pole, nechajte `""`.
  Ak je `{"data": {"items": [...]}}`, dajte `"data.items"`.
- `fields` priraďuje naše polia (vľavo) k názvom v odpovedi (vpravo), napr. `"route": "linka"`.
  Pole, ktoré zdroj nemá, nastavte na `""`.
- `delay_unit` je `"s"` alebo `"min"` podľa toho, v čom zdroj udáva meškanie.
- `speed_unit` je `"kmh"` alebo `"ms"`.
- `src_ts` je čas poslednej aktualizácie vozidla (unix sekundy). Ak ho zdroj má, skript
  nebude ukladať duplicitné záznamy, keď sa vozidlo nepohlo.

## Krok 5: Skúšobný zber

```bash
python collector.py --format json --vehicles-url "https://ADRESA" --mapping mapping.json --once
```

Pre GTFS-RT:

```bash
python collector.py --format gtfs-rt \
  --vehicles-url "URL_VEHICLE_POSITIONS" --trips-url "URL_TRIP_UPDATES" --once
```

Očakávaný výpis: `uložených 412 z 415 vozidiel`. Overenie:

```bash
python stats.py summary
```

Ak je počet uložených 0, skontrolujte mapovanie (hlavne `list_path`, `lat`, `lon`).
Ak zdroj vyžaduje API kľúč, pridajte `--header "Authorization: Bearer KLUC"`.

## Krok 6: Trvalý zber

Vynechajte `--once`. Predvolený interval je 60 s, minimálny povolený 10 s.
Odporúčané: `--retention-days 90` zmaže surové záznamy staršie ako 90 dní.

**Možnosť 1: jednoducho na pozadí (Linux/macOS)**
```bash
nohup python collector.py --format json --vehicles-url "URL" --mapping mapping.json \
  --retention-days 90 > collector.log 2>&1 &
```

**Možnosť 2: systemd (Linux server, preživí reštart)**
```bash
sudo cp -r . /opt/mhd-stats && cd /opt/mhd-stats
sudo useradd --system mhd && sudo chown -R mhd /opt/mhd-stats
# upravte URL a parametre v deploy/mhd-collector.service
sudo cp deploy/mhd-collector.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mhd-collector
sudo journalctl -u mhd-collector -f       # sledovanie logov
```

**Možnosť 3: Docker**
```bash
cp .env.example .env            # doplňte adresu a formát
cp mapping.example.json mapping.json
docker compose up -d
docker compose logs -f
```
Databáza je v `./data/mhd.sqlite`.

**Možnosť 4: Windows.** Spustite v PowerShelli príkaz z kroku 5 bez `--once` a okno nechajte otvorené,
prípadne použite Plánovač úloh (Task Scheduler) s akciou *Spustiť pri štarte*.

Zbierajte aspoň 2 – 4 týždne, aby štatistiky dávali zmysel (rozdiel dní v týždni, špičky).
Odhad veľkosti: ~500 vozidiel × 1 440 zberov denne ≈ 700 tis. riadkov, približne 50 – 70 MB denne.

## Krok 7: Štatistiky

```bash
python stats.py summary                       # prehľad databázy
python stats.py delay-by-route --days 30      # meškanie podľa liniek za 30 dní
python stats.py delay-by-hour                 # meškanie podľa hodiny dňa
python stats.py delay-by-weekday              # podľa dňa v týždni
python stats.py active-vehicles-by-hour       # priemerný počet vozidiel v prevádzke
python stats.py busiest-routes                # linky s najviac súčasnými vozidlami
python stats.py bottlenecks                   # miesta, kde vozidlá často stoja
python stats.py delay-by-hour --csv > hodiny.csv   # export pre Excel/Grafanu
```

Voľby: `--days N` (obdobie), `--min-samples N` (minimum vzoriek pre rebríček), `--tz` (časové pásmo,
predvolene Europe/Bratislava).

Poznámky k výsledkom:
- „Načas“ znamená meškanie od −60 s do +60 s, „do 5 min“ je 61 – 300 s, „nad 5 min“ viac.
- Zjavne chybné meškania (pod −30 min alebo nad +2 h) sa ignorujú.
- `bottlenecks` zahŕňa aj konečné a zastávky, kde vozidlá stoja prirodzene. Výsledok porovnajte s mapou.
- Presné meškanie voči cestovnému poriadku a ghost buses vyžadujú prepojenie s GTFS (ďalší vývoj).

Vlastné dotazy: `sqlite3 mhd.sqlite` alebo DB Browser for SQLite. Tabuľka `positions` má stĺpce
`ts, src_ts, vehicle_id, route, trip_id, vehicle_type, lat, lon, speed_kmh, delay_s`.

## Krok 8: Nahratie na GitHub (účet `lalasonycierny`)

1. Na github.com kliknite **New repository**, názov `mhd-stats`, nezaškrtávajte README ani
   `.gitignore` ani licenciu, potom **Create repository**.
2. Vytvorte prístup. GitHub už neprijíma heslo, použite jedno z:
   - **Personal Access Token:** Settings → Developer settings → Personal access tokens →
     Tokens (classic) → Generate new token, zaškrtnite `repo`. Token použijete ako heslo pri pushi.
   - **SSH kľúč:** `ssh-keygen -t ed25519`, obsah `~/.ssh/id_ed25519.pub` vložte do
     Settings → SSH and GPG keys. Potom použite adresu `git@github.com:lalasonycierny/mhd-stats.git`.
3. V priečinku projektu:
```bash
git init
git add .
git commit -m "Initial commit: MHD data collector"
git branch -M main
git remote add origin https://github.com/lalasonycierny/mhd-stats.git
git push -u origin main
```
Používateľské meno pri pushi je `lalasonycierny`, heslo je token. Ak git hlási, že nepozná autora:
`git config --global user.name "Meno"` a `git config --global user.email "email@example.com"`.

Súbor `.gitignore` zabráni nahratiu databázy, `.env` a `mapping.json`.

## Riešenie problémov

| Problém | Riešenie |
|---|---|
| `ModuleNotFoundError: requests` | Nie je aktivované virtuálne prostredie: `source .venv/bin/activate` a `pip install -r requirements.txt` |
| `uložených 0 z N` | Zlé mapovanie `lat`/`lon`, alebo zdroj vracia súradnice ako 0 |
| `uložených 0 z 0` | Zlý `list_path` alebo prázdna odpoveď zdroja |
| `zber zlyhal ... 403/401` | Zdroj vyžaduje kľúč (`--header`) alebo blokuje automatické požiadavky |
| `zber zlyhal ... 429` | Zvýšte `--interval` |
| Meškanie je prázdne (NULL) | Zdroj ho neposkytuje alebo je `delay_s` v mappingu prázdne. Pri GTFS-RT pridajte `--trips-url` |
| `no such table: positions` | Databáza ešte nevznikla, spustite najprv collector |
| Windows: chyba pri `Activate.ps1` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |

## Poznámky

- Dodržiavajte podmienky používania zdroja a nepreťažujte ho (interval aspoň 60 s).
- Zálohovanie: stačí skopírovať `mhd.sqlite` (najlepšie po zastavení zberu).
- GTFS-realtime vetva je napísaná podľa špecifikácie, ale v tomto balíku ju pokrýva
  len kontrola syntaxe. JSON vetva a štatistiky sú pokryté `tests/selftest.py`.

Licencia: MIT
