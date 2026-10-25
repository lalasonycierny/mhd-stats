# Štatistiky MHD Bratislava

Automaticky generované 2026-10-25 05:30. Zdroj: kdejemhd.sk, zber každú minútu.

- Dní v štatistike: **1** (2026-10-25 až 2026-10-25)
- Priemerné pokrytie zberom: **2 %** (100 % = zber každú minútu celý deň)
- Posledných 7 dní: načas 45.9 %, meškanie 5 min a viac 38.3 %, v službe priemerne 384 vozidiel (9 987 meraní).

## Vývoj v čase

![presnosť](charts/daily_punctuality.png)

![vozidlá](charts/daily_vehicles.png)

## Kedy meškajú najviac

![heatmapa](charts/heatmap_delay_weekday_hour.png)

![vozidlá podľa hodiny](charts/vehicles_by_hour.png)

## Linky s najväčším podielom meškaní (30 dní)

| Linka | Meraní | Načas % | 5 min+ % | Priem. meškanie (min) |
|---|---|---|---|---|
| 147 | 26 | 0.0 | 100.0 | 15.0 |
| 163 | 26 | 0.0 | 100.0 | 15.0 |
| 191 | 52 | 0.0 | 100.0 | 15.0 |
| 192 | 26 | 0.0 | 100.0 | 15.0 |
| 33 | 26 | 0.0 | 100.0 | 15.0 |
| 69 | 26 | 0.0 | 100.0 | 15.0 |
| 77 | 26 | 0.0 | 100.0 | 15.0 |
| 90 | 52 | 0.0 | 100.0 | 15.0 |
| 94 | 26 | 0.0 | 100.0 | 15.0 |
| 95 | 26 | 0.0 | 100.0 | 15.0 |

![linky](charts/worst_routes.png)

## Podľa typu vozidla (30 dní)

| Typ | Meraní | Načas % | 5 min+ % |
|---|---|---|---|
| Autobusy | 6147 | 43.8 | 40.6 |
| Tramvaje | 2001 | 38.8 | 42.4 |
| Trolejbusy | 1839 | 60.8 | 26.1 |

## Miesta, kde vozidlá stoja

![miesta](charts/hotspots.png)

Zahŕňa aj konečné a zastávky, kde vozidlá stoja prirodzene.

## Dáta na stiahnutie

Denné agregáty vo formáte CSV (zostávajú v repozitári natrvalo):

- [daily.csv](data/daily.csv) celkové údaje po dňoch
- [daily_route.csv](data/daily_route.csv) po linkách
- [daily_hour.csv](data/daily_hour.csv) po hodinách
- [daily_type.csv](data/daily_type.csv) po type vozidla
- [daily_hotspots.csv](data/daily_hotspots.csv) miesta, kde vozidlá stoja

## Poznámky k metodike

- Meškanie zdroj udáva v celých minútach. Hodnota 15:00 vyzerá ako strop, takže priemerné meškanie je orezané a presnejšie sú podiely. Stĺpec `pct_cap15` v CSV ukazuje podiel hodnôt na strope.
- „Načas“ je meškanie pod 1 minútu, „5 min a viac“ zodpovedá kategórii „nad 5 min“ na webe.
- Do štatistík meškaní sa počítajú len vozidlá, ktoré majú údaj o meškaní (sú na spoji).
- Dni sa počítajú v čase Europe/Bratislava. Pokrytie pod 100 % znamená výpadky zberu.
- Nezávislý projekt, nie je súčasťou Dopravného podniku Bratislava.
