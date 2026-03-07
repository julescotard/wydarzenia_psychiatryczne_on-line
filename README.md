# wydarzenia_psychiatryczne_on-line

Automatyczne wyszukiwanie i aktualizacja listy **psychiatrycznych wydarzeń w Polsce** (online/VOD).  
Repo publikuje plik **iCalendar (.ics)** przez GitHub Pages, aby dało się go **zasubskrybować na iPhonie**.

## Kryteria
- `wydarzenia_psychiatryczne_on-line`:
  - LIVE online lub VOD/nagrania po wydarzeniu (hybrydy też OK).
- Wyniki mogą się dublować między kalendarzami on-line/off-line (zgodnie z założeniem).

## Jak uruchomić (krok po kroku)
1) Utwórz repo **Public** o nazwie: `wydarzenia_psychiatryczne_on-line`  
2) Wgraj zawartość tego ZIP do repo (Upload files).  
3) Włącz GitHub Pages: **Settings → Pages → Deploy from a branch → main /docs**  
4) Uruchom workflow pierwszy raz: **Actions → Update psychiatry events… → Run workflow**

## Link do kalendarza (iPhone)
- HTTPS: `https://julescotard.github.io/wydarzenia_psychiatryczne_on-line/psychiatria.ics`  
- WEBCAL: `webcal://julescotard.github.io/wydarzenia_psychiatryczne_on-line/psychiatria.ics`

## iPhone 15 Pro — dodanie subskrypcji
Ustawienia → Aplikacje → Kalendarz → Konta → Dodaj konto → Inne → **Dodaj subskrybowany kalendarz** → wklej URL.

## Aktualizacje i powiadomienia
- Workflow uruchamia się **raz w miesiącu (1. dzień miesiąca)**.
- Jeśli wykryje **nowe/zmienione/usunięte** wydarzenia → aktualizuje `.ics` i tworzy **Issue** z listą zmian + linkami.
- Jeśli nie ma zmian → robi **keepalive commit** do `docs/keepalive.txt`, żeby GitHub nie wyłączył harmonogramu z braku aktywności.

## Linki do znalezionych wydarzeń
- aktualna lista (HTML): `https://julescotard.github.io/wydarzenia_psychiatryczne_on-line/events.html`
- historia zmian: zakładka **Issues** w repo (tylko gdy są zmiany).
