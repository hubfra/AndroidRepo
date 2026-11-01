# Statystyki meczowe

Strona (PWA) z zestawieniem statystyk drużyn grających danego dnia w topowej
piątce lig europejskich (Anglia, Hiszpania, Włochy, Niemcy, Francja).

Dla każdego meczu, po kliknięciu:
- **ostatnie 10 meczów ligowych** każdej drużyny – średnia i wykres słupkowy,
- **H2H z ostatnich 2 lat** (mecze ligowe) – porównanie obu drużyn mecz po meczu.

Obecnie liczona statystyka: **rzuty rożne wywalczone przez drużynę**.

## Jak to działa

1. GitHub Actions (`.github/workflows/update.yml`) codziennie ok. 5:15/6:15
   czasu polskiego uruchamia `scripts/fetch_data.py`.
2. Skrypt pobiera z [API-Football](https://www.api-football.com) mecze z dnia,
   terminarze lig i statystyki zakończonych meczów, a wynik zapisuje do
   `site/data/matches.json`. Pobrane statystyki są zapamiętywane (cache), więc
   każdego dnia pobierane są tylko nowe mecze.
3. Katalog `site/` jest publikowany na GitHub Pages.

Aktualizację można też uruchomić ręcznie: zakładka **Actions → Aktualizacja
statystyk → Run workflow** (opcjonalnie z datą, np. `2026-11-08`).

## Dodawanie statystyk

W `config.json`, w tablicy `stats`, dopisz wpis, np.:

```json
{ "key": "offsides", "api_type": "Offsides", "label": "Spalone" }
```

Gotowe przykłady są w `available_stats_examples`. Cache przechowuje wszystkie
statystyki z API, więc nowa statystyka nie wymaga ponownego pobierania danych.

## Konfiguracja (jednorazowo)

1. Załóż darmowe konto na <https://dashboard.api-football.com/register> i skopiuj
   klucz API z zakładki **Account → My Access**.
2. W repozytorium na GitHubie: **Settings → Secrets and variables → Actions →
   New repository secret**, nazwa `API_FOOTBALL_KEY`, wartość: klucz.
3. **Settings → Pages → Build and deployment → Source: GitHub Actions**.
   GitHub Pages w darmowym planie działa tylko dla repozytoriów publicznych
   (Settings → General → Danger Zone → Change visibility). Klucz API pozostaje
   tajny – jest tylko w Secrets.
4. Uruchom workflow ręcznie (Actions → Aktualizacja statystyk → Run workflow).
   Adres strony pojawi się w Settings → Pages.
5. Na telefonie otwórz stronę w Chrome → menu ⋮ → **Dodaj do ekranu głównego**.

## Plan płatny API-Football

Darmowy plan: 100 zapytań dziennie, ok. 10 na minutę. Przy płatnym planie:

1. Zaloguj się na <https://dashboard.api-football.com>.
2. Wejdź w **Subscriptions** (Subskrypcje) i wybierz plan, np. **Pro**
   (ok. 19 USD/mies., 7 500 zapytań dziennie). Zapłać kartą. Klucz API się
   nie zmienia.
3. Kupuj bezpośrednio na api-football.com, a nie przez RapidAPI – tam jest
   inny klucz i inny adres API.
4. W repozytorium: **Settings → Secrets and variables → Actions → Variables**
   dodaj `REQUEST_DELAY` = `0.3` oraz `MAX_REQUESTS` = `1000`, żeby skrypt
   działał szybciej i mógł pobrać więcej.

## Lokalnie

```bash
python3 scripts/fetch_data.py --mock --date 2026-11-01   # dane testowe, bez API
python3 -m http.server -d site 8000                       # http://localhost:8000
python3 -m unittest discover -s tests                     # testy
```
