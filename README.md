# mhd-stats

Dlhodobý zber polôh a meškaní vozidiel MHD v Bratislave (zdroj: JSON API webu `kdejemhd.sk`)
do SQLite a jednoduché štatistiky: meškania podľa linky, typu, hodiny a dňa, počet vozidiel
v službe, miesta, kde vozidlá často stoja.

Nezávislý projekt, nie je súčasťou Dopravného podniku Bratislava.

<!-- STATS:START -->
## Aktuálne štatistiky

Posledných 7 dní: načas 44.6 %, meškanie 5 min a viac 34.1 %, v službe priemerne 391 vozidiel (408 948 meraní).

![presnosť](stats/charts/daily_punctuality.png)

Všetko: [stats/STATS.md](stats/STATS.md)
<!-- STATS:END -->

## Obsah

| Súbor | Účel |
|---|---|
| `collector.py` | zber dát do SQLite (JSON API alebo GTFS-realtime) |
| `stats.py` | štatistické prehľady z databázy (výpis v konzole) |
| `publish.py` | denné agregáty do CSV, grafy, report `stats/STATS.md` a nahratie na GitHub |
| `run_collector.bat`, `publish_daily.bat` | spúšťače pre Windows (zber a denný upload) |
| `mapping.kdejemhd.json` | hotové mapovanie polí pre `kdejemhd.sk` |
| `mapping.example.json` | vzor pre iný JSON zdroj |
| `tests/selftest.py`, `tests/test_publish.py` | testy bez internetu |
| `deploy/` | systemd služba zberu a časovač denného uploadu |
| `Dockerfile`, `docker-compose.yml`, `.env.example` | beh v Dockeri |

## Čo vieme o zdroji dát

Adresa: `https://kdejemhd.sk/api/vehicles?type=T` (a rovnako `type=O`, `type=A`). Odpoveď je JSON
`{"data": [...], "source": "live", "cached": false}`. Každé vozidlo obsahuje:

| Pole zdroja | Význam | Poznámka |
|---|---|---|
| `Key` | ID vozidla | stabilné, vhodné na sledovanie vozidla |
| `LineName` | linka | |
| `TransportTypeName` | typ dopravy | `type=T` vracia „Autobusy“ |
| `Location.Latitude/Longitude` | poloha | |
| `Delay` | meškanie ako text `M:SS` | `null` = vozidlo nie je na spoji |
| `State` | 0 načas, 1 do 5 min, 2 nad 5 min | zhoduje sa s farbami na webe |
| `FinalStationName` | cieľová zastávka (smer) | |
| `Azimuth` | smer jazdy | hodnota 510 je neplatná, ukladá sa ako NULL |
| `VehicleNumber`, `VehicleRegistrationNumber`, `CourseName`, `StationName` | | v ukážke boli vždy `null` |

Dôležité vlastnosti dát, s ktorými treba rátať:
- **Meškanie je len v celých minútach** a **hodnota `15:00` vyzerá ako strop** (v ukážke sa vyskytovala
  veľmi často, aj pri vozidlách stojacich pri sebe na jednom mieste, kde ide pravdepodobne o vozidlá pred
  odchodom alebo v depe). Preto `stats.py` ukazuje samostatný stĺpec `pct_15min_strop` a má voľbu
  `--exclude-capped`. Pred vážnymi závermi hodnoty overte voči GTFS cestovnému poriadku.
- **Priemerné meškanie je zhora orezané** týmto stropom, berte ho ako orientačné. Presnejšie sú
  podiely (`pct_nacas`, `pct_5min_plus`).
- **Chýbajúce meškanie (`null`) býva pri vozidlách mimo spoja** (depo, presun). Štatistiky meškaní ich
  vynechávajú, `--only-in-service` ich pri zbere vôbec neukladá.
- **Zdroj nemá rýchlosť ani čas poslednej aktualizácie vozidla.** Stojace vozidlá sa preto zisťujú z toho,
  že sa poloha medzi dvoma zbermi nezmenila.
- Časť záznamov má súradnice zaokrúhlené na 5 desatinných miest a azimut 510. Môže ísť o iný zdroj polohy
  (napr. odhad). Stĺpec `azimuth` umožňuje také záznamy neskôr odfiltrovať.
- Hodnoty `type=O` a `type=A` som ešte nevidel. Predpokladám rovnakú štruktúru. Overenie je v kroku 3.

---

# DETAILNÝ POSTUP

## Krok 1: Príprava počítača

Potrebujete **Python 3.9 alebo novší** a **git**.

- **Windows:** Python z python.org (pri inštalácii zaškrtnite *Add Python to PATH*), git z git-scm.com.
- **macOS:** `brew install python git`
- **Linux (Debian/Ubuntu):** `sudo apt install python3 python3-venv git`

Overenie: `python --version` (na Linuxe/macOS `python3 --version`) a `git --version`.

## Krok 2: Inštalácia

V priečinku projektu (`mhd-repo`):

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows (CMD)
# .venv\Scripts\Activate.ps1    # Windows (PowerShell)
# source .venv/bin/activate     # Linux / macOS
pip install -r requirements.txt
python tests/selftest.py        # očakávaný výstup: OK: všetky testy prešli
python tests/test_publish.py    # OK: publish test prešiel
```

Na Linuxe/macOS používajte `python3` namiesto `python`.

## Krok 3: Overenie troch adries

Otvorte v prehliadači tieto tri adresy a skontrolujte, že každá vracia JSON so zoznamom `data`:

```
https://kdejemhd.sk/api/vehicles?type=T
https://kdejemhd.sk/api/vehicles?type=O
https://kdejemhd.sk/api/vehicles?type=A
```

Pozrite sa na `TransportTypeName` (T = Autobusy). Zvyšné dve by mali byť trolejbusy a električky.
Ak má niektorá iné názvy polí, upravte `mapping.kdejemhd.json` (viď „Úprava mapovania“ nižšie).

## Krok 4: Skúšobný zber

```bash
python collector.py --format json --mapping mapping.kdejemhd.json ^
  --vehicles-url "https://kdejemhd.sk/api/vehicles?type=T" ^
  --vehicles-url "https://kdejemhd.sk/api/vehicles?type=O" ^
  --vehicles-url "https://kdejemhd.sk/api/vehicles?type=A" --once
```

(Na Linuxe/macOS namiesto `^` na konci riadku použite `\`. Vo Windows PowerShell je to znak `` ` ``.
Alebo celý príkaz zapíšte na jeden riadok.)

Očakávaný výpis: `uložených 650 z 650 vozidiel` (číslo sa líši). Potom:

```bash
python stats.py summary
python stats.py delay-by-type --min-samples 1
```

Ak je počet uložených 0, skontrolujte mapovanie. Ak jeden zdroj zlyhá, výpis to uvedie a uložia sa ostatné.

## Krok 5: Trvalý zber

Zoberte príkaz z kroku 4 bez `--once` a pridajte:
- `--only-in-service` ukladá len vozidlá na spoji (približne o polovicu menej dát),
- `--retention-days 60` maže surové záznamy staršie ako 60 dní.

**Veľkosť dát (zmerané):** približne 125 bajtov na záznam. Pri ~650 vozidlách a zbere každú minútu je to
asi 115 MB denne (3,5 GB mesačne). S `--only-in-service` zhruba polovica. Prenos je približne 3 × 150 kB za
minútu, teda okolo 650 MB denne.

**Možnosť A: Windows.** Použite `run_collector.bat` (sám zber reštartuje, ak spadne). Automatické spustenie po
prihlásení a denný upload na GitHub sú v kroku 6.

**Možnosť B: Linux/macOS na pozadí**
```bash
nohup python collector.py --format json --mapping mapping.kdejemhd.json \
  --vehicles-url "https://kdejemhd.sk/api/vehicles?type=T" \
  --vehicles-url "https://kdejemhd.sk/api/vehicles?type=O" \
  --vehicles-url "https://kdejemhd.sk/api/vehicles?type=A" \
  --only-in-service --retention-days 60 > collector.log 2>&1 &
```

**Možnosť C: systemd (Linux server, preživí reštart)**
```bash
sudo cp -r . /opt/mhd-stats && cd /opt/mhd-stats
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
sudo useradd --system mhd && sudo chown -R mhd /opt/mhd-stats
sudo cp deploy/mhd-collector.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now mhd-collector
sudo journalctl -u mhd-collector -f
```

**Možnosť D: Docker**
```bash
cp .env.example .env
docker compose up -d
docker compose logs -f
```
Databáza je v `./data/mhd.sqlite`.

Zbierajte aspoň 2 až 4 týždne, aby štatistiky dávali zmysel (dni v týždni, špičky, sviatky).

## Krok 6: Automatický zber a denné nahrávanie štatistík na GitHub

**Ako to funguje.** Zber beží nepretržite na jednom počítači a každú minútu ukladá dáta do `mhd.sqlite`.
Raz denne sa spustí `publish.py`, ktorý:
1. vypočíta agregáty za každý dokončený deň a pridá ich do malých CSV v `stats/data/` (tie zostávajú
   v repozitári navždy, aj keď sa surové záznamy po 60 dňoch mažú),
2. vykreslí grafy do `stats/charts/` a zostaví report `stats/STATS.md`,
3. aktualizuje sekciu „Aktuálne štatistiky“ na úvodnej stránke README (medzi značkami `STATS:START` a `STATS:END`),
4. urobí `git pull --rebase`, commit a `git push`.

Surová databáza sa na GitHub **nenahráva** (je veľká a je v `.gitignore`), nahrávajú sa len agregáty a grafy
(približne 1 – 2 MB za mesiac pri CSV, grafy pri nahrávaní raz týždenne okolo 1 MB týždenne).

**Prečo nie GitHub Actions?** Plánované úlohy na GitHube sa dajú spúšťať najčastejšie raz za 5 minút a
často sa oneskorujú. Zber každú minútu preto musí bežať na vlastnom počítači, ktorý je stále zapnutý
(domáci PC, Raspberry Pi alebo lacný server). Pokrytie zberu sa ukladá do štatistík, takže výpadky sú vidieť.

### Windows (váš prípad)

Predpoklady: počítač nesmie zaspávať (Nastavenia, Napájanie a spánok, Nikdy) a projekt musí byť naklonovaný
z GitHubu (priečinok `mhd-repo`), aby `git push` fungoval. Prihlásenie na GitHub ste už urobili, Git Credential
Manager si ho pamätá.

1. Skúška ručne: dvakrát kliknite na `run_collector.bat`. Otvorí sa okno so zberom. Nechajte ho bežať pár minút
   a skontrolujte `collector.log`.
2. Skúška uploadu (po prvom dokončenom dni, teda najskôr nasledujúci deň): v priečinku projektu spustite
   `publish_daily.bat` a pozrite `publish.log`. Na GitHube sa objaví priečinok `stats`.
3. Automatické spúšťanie. V CMD spustite (cestu upravte na váš priečinok, napr. `C:\Users\user\mhd-stats\mhd-repo`):

```
schtasks /Create /TN "mhd-collector" /TR "\"C:\Users\user\mhd-stats\mhd-repo\run_collector.bat\"" /SC ONLOGON
schtasks /Create /TN "mhd-publish" /TR "\"C:\Users\user\mhd-stats\mhd-repo\publish_daily.bat\"" /SC DAILY /ST 03:30
```

   Zber sa spustí po prihlásení do Windowsu, upload každý deň o 03:30. V Plánovači úloh (Task Scheduler) môžete
   pri úlohe `mhd-publish` v nastaveniach zaškrtnúť „Spustiť úlohu čo najskôr po zmeškanom spustení“.
4. Ak sa počítač vypne, zber sa preruší. Štatistiky to zohľadnia (pokrytie), ale dáta za ten čas sa nedoplnia.

### Linux server alebo Raspberry Pi

```bash
sudo git clone https://github.com/lalasonycierny/mhd-stats.git /opt/mhd-stats
cd /opt/mhd-stats
sudo python3 -m venv .venv && sudo .venv/bin/pip install -r requirements.txt
sudo useradd --system --create-home mhd && sudo chown -R mhd /opt/mhd-stats
sudo cp deploy/mhd-collector.service deploy/mhd-publish.service deploy/mhd-publish.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mhd-collector mhd-publish.timer
```

Pre `git push` z používateľa `mhd` vytvorte deploy kľúč: `sudo -u mhd ssh-keygen -t ed25519`, verejný kľúč pridajte v repozitári
na GitHube (Settings, Deploy keys, zaškrtnúť Allow write access) a nastavte remote na SSH:
`sudo -u mhd git -C /opt/mhd-stats remote set-url origin git@github.com:lalasonycierny/mhd-stats.git`.
Tiež nastavte `git config user.name` a `user.email` pre tohto používateľa.

### Voľby `publish.py`

| Voľba | Význam |
|---|---|
| `--push` | po vytvorení urobí commit a push |
| `--charts-weekday 0` | grafy a report obnoví len v pondelok (CSV sa dopĺňa denne). Bez voľby sa obnovujú denne |
| `--no-charts` | len CSV |
| `--min-coverage 0.5` | dni s pokrytím zberom pod 50 % sa nezobrazia v grafe vývoja |
| `--window-days 90` | okno pre heatmapu a graf podľa hodiny |
| `--include-today` | náhľad: spracuje aj dnešný neúplný deň (po skončení dňa sa automaticky prepočíta znova) |
| `--reprocess` | znova prepočíta všetky dni, ktoré sú ešte v databáze (po zmene logiky) |

Prvý beh `publish.py` spracuje všetky dokončené dni od začiatku zberu. Dnešný deň sa spracuje až po polnoci.
Ak je zbierané menej než deň, výpis v `publish.log` bude `nových dní: 0` a `zatiaľ nie sú dáta pre report`, čo je v poriadku.
Náhľad grafov hneď: `python publish.py --repo . --push --include-today --min-coverage 0 --min-route-samples 1 --hotspot-min 2`.

### Čo sa nahráva na GitHub

- `stats/STATS.md` report s grafmi a tabuľkami (otvorí sa priamo na GitHube),
- `stats/charts/*.png` grafy: presnosť po dňoch, počet vozidiel po dňoch, heatmapa meškaní (deň v týždni a hodina),
  vozidlá podľa hodiny, najhoršie linky, miesta kde vozidlá stoja,
- `stats/data/*.csv` denné agregáty, z ktorých sa dajú robiť vlastné analýzy aj po zmazaní surových dát.

## Krok 7: Štatistiky v konzole

```bash
python stats.py summary                       # prehľad databázy
python stats.py delay-by-route --days 30      # meškanie podľa liniek za 30 dní
python stats.py delay-by-type                 # podľa typu vozidla
python stats.py delay-by-hour                 # podľa hodiny dňa
python stats.py delay-by-weekday              # podľa dňa v týždni
python stats.py active-vehicles-by-hour       # vozidlá v službe a všetky, priemer podľa hodiny
python stats.py busiest-routes                # linky s najviac súčasnými vozidlami v službe
python stats.py bottlenecks                   # miesta, kde vozidlá na spoji stoja
python stats.py delay-by-hour --csv > hodiny.csv     # export pre Excel/Grafanu
```

Voľby: `--days N` (obdobie), `--min-samples N` (minimum vzoriek pre rebríček), `--exclude-capped`
(vynechá meškania od 15 min), `--tz` (predvolene Europe/Bratislava), `--csv`.

Stĺpce meškaní: `pct_nacas` je podiel vozidiel s meškaním pod 1 min, `pct_1_az_4min` 1 až 4 min,
`pct_5min_plus` 5 min a viac (to je „nad 5 min“ na webe), `pct_15min_strop` podiel hodnôt na strope 15:00.

Poznámky:
- Veľa vzoriek na konečných a v depách je normálne. `bottlenecks` preto čítajte spolu s mapou.
- `bottlenecks` používa okenné funkcie SQLite (potrebná verzia 3.25 alebo novšia, Python 3.9+ ju má).
- Vlastné dotazy: `sqlite3 mhd.sqlite` alebo DB Browser for SQLite. Tabuľka `positions` má stĺpce
  `ts, src_ts, vehicle_id, route, trip_id, vehicle_type, lat, lon, speed_kmh, azimuth, delay_s, state, final_station`.
- Ghost buses a presné meškanie voči cestovnému poriadku vyžadujú prepojenie s GTFS (ďalší krok vývoja).

## Úprava mapovania

`mapping.kdejemhd.json`: `list_path` je cesta k poľu vozidiel (`data`). V `fields` je vľavo naše pole,
vpravo cesta v odpovedi s bodkou pre vnorené polia (`Location.Latitude`). Prázdny reťazec znamená, že
zdroj pole nemá. `delay_unit` je `mmss` (text `M:SS`), `min` alebo `s`. `speed_unit` je `kmh` alebo `ms`.

## Krok 8: Aktualizácia kódu v repozitári na GitHube

Po zmenách v súboroch:

```bash
git add .
git commit -m "Update collector for kdejemhd.sk API"
git push
```

Ak `git push` odmietne zmeny (`rejected`), spustite najprv `git pull --rebase` a potom `git push`.
Pri prihlásení použite meno `lalasonycierny` a Personal Access Token namiesto hesla.

Prvé nahratie (nový priečinok bez histórie):
```bash
git clone https://github.com/lalasonycierny/mhd-stats.git mhd-repo
# skopírujte súbory z balíka do mhd-repo (vrátane skrytých .gitignore a .env.example), potom:
cd mhd-repo && git add . && git commit -m "Initial commit" && git push
```

## Riešenie problémov

| Problém | Riešenie |
|---|---|
| `ModuleNotFoundError: requests` | Nie je aktívne virtuálne prostredie, spustite `activate` a `pip install -r requirements.txt` |
| `uložených 0 z 0` | Zlý `list_path`, alebo adresa vracia chybu. Otvorte ju v prehliadači |
| `uložených 0 z N` | Zlé mapovanie `lat`/`lon` |
| `zlyhalo ... 403/401` | Zdroj blokuje automatické požiadavky alebo vyžaduje kľúč (`--header`) |
| `zlyhalo ... 429` | Zvýšte `--interval` |
| Meškania sú prázdne | Zdroj ich neposkytuje, alebo je `delay_s` v mappingu prázdne |
| `no such table: positions` | Databáza ešte nevznikla, spustite najprv collector |
| Windows: chyba pri `Activate.ps1` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `no such function: LAG` | Stará verzia SQLite, aktualizujte Python na 3.9 alebo novší |

## Poznámky

- Ide o interné API webu `kdejemhd.sk`, nie o oficiálny open data feed. Držte interval aspoň 60 s, nesťahujte
  častejšie než je potrebné a ideálne sa autorovi webu ozvite (kontakt na jeho GitHube v pätičke stránky)
  alebo zvážte oficiálny zdroj dát Dopravného podniku Bratislava.
- Zálohovanie: stačí skopírovať `mhd.sqlite` (najlepšie po zastavení zberu).
- Vetva GTFS-realtime je napísaná podľa špecifikácie, ale v tomto balíku ju pokrýva len kontrola syntaxe.
  JSON vetva a štatistiky pokrýva `tests/selftest.py` na údajoch vo formáte `kdejemhd.sk`.

Licencia: MIT
