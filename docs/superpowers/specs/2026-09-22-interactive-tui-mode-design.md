# Interactive TUI mode for anonymize.py

Data: 2026-09-22
Status: zatwierdzony

## Kontekst

`anonymize.py` jest dziś uruchamiany wyłącznie jako klasyczny CLI:
`anonymize.py <source> <replacements.json> [--output <dir>]`. Wszystkie
argumenty trzeba znać i wpisać z góry, a zarządzanie plikiem
`replacements.json` (dodawanie/edycja/usuwanie wpisów) odbywa się dziś
ręcznie, poza narzędziem, w dowolnym edytorze tekstu.

## Cel

Dodać tryb interaktywny (TUI), uruchamiany automatycznie gdy skrypt
wywołany jest **bez żadnych argumentów**, który prowadzi użytkownika
przez: wybór/utworzenie pliku słownika, przegląd i edycję jego zawartości
wprost z konsoli, wybór folderu źródłowego przez nawigowalną przeglądarkę
katalogów, potwierdzenie folderu wyjściowego, i uruchomienie tej samej
anonimizacji co dotychczasowy CLI.

## Zakres

### W zakresie

- **Wyzwalanie trybu:** `python anonymize.py` (zero argumentów) uruchamia
  tryb interaktywny. Wywołanie z argumentami działa dokładnie tak jak
  dziś — tryb klasyczny/skryptowalny pozostaje bez zmian, do automatyzacji
  i istniejących wywołań.
- **Krok 1 — plik słownika:** przeglądarka plików ograniczona do
  katalogów i plików `.json`, z dodatkową opcją "utwórz nowy plik
  słownika tutaj" (tworzy pusty `{}` pod wskazaną nazwą we wskazanym
  katalogu).
- **Krok 2 — zarządzanie słownikiem:** pętla wyświetlająca aktualne wpisy
  (`klucz -> wartość`) i menu akcji: Dodaj wpis / Edytuj wpis / Usuń wpis
  / Kontynuuj.
  - **Dodaj wpis:** pyta o klucz (tekst), potem o wartość (tekst).
  - **Edytuj wpis:** pokazuje listę istniejących kluczy do wyboru, potem
    pyta wyłącznie o **nową wartość** dla wybranego klucza (pole
    wstępnie wypełnione dotychczasową wartością) — sam klucz się nie
    zmienia; zmiana klucza to w praktyce usunięcie starego wpisu i
    dodanie nowego, dwoma osobnymi akcjami.
  - **Usuń wpis:** pokazuje listę istniejących kluczy do wyboru, usuwa
    wybrany.

  **Każda zmiana jest natychmiast zapisywana** do pliku na dysku (nie
  dopiero po zakończeniu sesji) — przerwanie sesji w dowolnym momencie
  nie cofa zmian już wykonanych.

  Wybranie **Edytuj wpis** lub **Usuń wpis**, gdy słownik jest pusty,
  wypisuje `"Brak wpisów."` i wraca do menu (bez próby pokazania pustej
  listy wyboru) — wszystkie cztery opcje menu są zawsze widoczne,
  niezależnie od tego czy słownik ma jakiekolwiek wpisy.
- **Krok 3 — folder źródłowy:** nawigowalna przeglądarka katalogów
  (strzałki + Enter): lista podfolderów bieżącego katalogu jako opcje
  wyboru, `..` żeby wyjść wyżej, `✓ Wybierz ten folder` żeby zatwierdzić
  bieżący katalog jako źródło.
- **Krok 4 — folder wyjściowy:** domyślna wartość identyczna jak w CLI
  (`<source-parent>/anonimized/<source-name>`), z opcją zmiany przez tę
  samą przeglądarkę katalogów co w kroku 3.
- **Krok 5 — potwierdzenie i uruchomienie:** ekran podsumowania (folder
  źródłowy, folder wyjściowy, liczba wpisów słownika) z pytaniem
  potwierdzającym, następnie uruchomienie **dokładnie tego samego**
  silnika skanowania/przetwarzania/podsumowania co tryb CLI (pasek
  postępu, podsumowanie na końcu — bez zmian).
- **Refaktoryzacja:** wydzielenie obecnej logiki `main()` (skan → przetwarzanie
  → podsumowanie, wszystko po ustaleniu `source_dir`/`replacements_file`/
  `output_root`) do osobnej funkcji `run_anonymization(source_dir,
  replacements_file, output_root)`, używanej przez oba tryby (CLI i
  interaktywny) — bez duplikowania logiki.
- **Biblioteka:** `questionary` (nowa zależność pip, dopisana do
  `requirements.txt`). Przeglądarka katalogów/plików to własna pętla
  zbudowana na `questionary.select` z `questionary.Choice(title=, value=)`
  (wartości jako pary `(akcja, cel)`, bez parsowania tekstu wyświetlanego
  użytkownikowi).
- **Struktura plików:** cały nowy kod w `anonymize.py` — świadoma decyzja
  (jeden plik), nie w osobnym module.
- **Obsługa błędów:**
  - Ctrl-C w dowolnym kroku (questionary zwraca `None` z `.ask()`) kończy
    tryb interaktywny czytelnym komunikatem "Anulowano.", bez tracebacku.
  - Brak uprawnień przy listowaniu zawartości katalogu — czytelny
    komunikat, użytkownik może cofnąć się wyżej zamiast programu, który
    się wywala.
  - Brak zainstalowanego `questionary` przy starcie bez argumentów —
    czytelny komunikat `"Interactive mode requires questionary. Install
    it with: pip install questionary"`, zgodnie z istniejącym wzorcem dla
    opcjonalnych zależności (Tesseract, pymupdf).
- **Testowanie:** mockowanie `questionary.select`/`text`/`confirm`, żeby
  przetestować logikę kreatora (dodawanie/edycja/usuwanie wpisów, zapis do
  pliku po każdej zmianie, nawigacja w przeglądarce) bez realnego
  terminala — ten sam wzorzec co reszta testów w projekcie.

### Poza zakresem (świadomie pominięte)

- Zmiana zachowania trybu CLI z argumentami — zero zmian.
- Możliwość uruchomienia SAMEGO zarządzania słownikiem bez późniejszego
  przetwarzania folderu (np. osobna flaga "tylko edytuj słownik i wyjdź")
  — kreator jest liniowy, zawsze kończy się (opcjonalnym) uruchomieniem
  anonimizacji; wyjście wcześniej odbywa się przez Ctrl-C/anulowanie.
- Wybór/podgląd pojedynczych plików w przeglądarce folderu źródłowego —
  przeglądarka z kroku 3 pokazuje i pozwala wybierać wyłącznie foldery,
  tak jak dziś robi to argument `source` w CLI (cały folder, nie
  pojedyncze pliki).
- Walidacja/podgląd zawartości pliku słownika inna niż podstawowa
  (np. wykrywanie duplikatów kluczy różniących się wielkością liter) —
  zarządzanie słownikiem operuje na zwykłym słowniku Pythona, tak samo
  jak dzisiejsze ręczne edytowanie pliku JSON.
- Multi-select / wsadowe operacje na wielu wpisach słownika naraz —
  jeden wpis na akcję (dodaj/edytuj/usuń), zgodnie z tym co zostało
  opisane w prośbie.

## Architektura i przepływ

```
python anonymize.py                          (0 argumentów)
    |
    v
run_interactive_mode()
    |
    +-- browse_for_replacements_file(cwd)      -> Path do pliku .json
    |
    +-- manage_replacements_dictionary(path)   -> dict (petla: Dodaj/Edytuj/Usun/Kontynuuj,
    |                                              zapis do pliku po kazdej zmianie)
    |
    +-- browse_for_directory(cwd)               -> Path folderu zrodlowego
    |
    +-- prompt_output_directory(default)        -> Path folderu wyjsciowego
    |
    +-- questionary.confirm(podsumowanie)       -> jesli nie: "Anulowano.", return
    |
    v
run_anonymization(source_dir, replacements_file, output_root)
    (dokladnie ten sam kod co dzisiejszy main() po walidacji argumentow:
     skan -> deduplikacja -> anonimizacja nazw -> przetwarzanie -> podsumowanie)
```

`main()` po zmianie:

```python
def main():
    if len(sys.argv) == 1:
        run_interactive_mode()
        return

    parser = argparse.ArgumentParser(...)
    args = parser.parse_args()
    # ... istniejaca walidacja source_dir / replacements_file / output_root ...
    run_anonymization(source_dir, replacements_file, output_root)
```

## Komponenty

- `browse_for_directory(start_path: Path) -> Path` — nawigowalna
  przeglądarka katalogów, zwraca wybrany folder. Pętla: listuje
  podfoldery `start_path`/bieżącego katalogu, renderuje jako
  `questionary.select` z opcjami `[Wybierz ten folder]`, `..` (jeśli nie
  jesteśmy w katalogu głównym), oraz po jednej opcji na podfolder.
  Wybranie podfolderu aktualizuje bieżący katalog i renderuje ponownie.
- `browse_for_replacements_file(start_path: Path) -> Path` — jak wyżej,
  ale listuje też pliki `.json` (nie tylko foldery) jako wybieralne, plus
  opcję `+ Utwórz nowy plik słownika tutaj` (pyta o nazwę pliku, tworzy
  `{}`, zwraca ścieżkę).
- `manage_replacements_dictionary(replacements_path: Path) -> dict` —
  wczytuje JSON z pliku **raz**, na wejściu do funkcji; od tego momentu
  słownik w pamięci jest jedynym źródłem prawdy w obrębie tej pętli
  (nie jest ponownie wczytywany z dysku między krokami — sesja
  interaktywna jest jednowątkowa, nic innego nie modyfikuje pliku w
  tym czasie). Pętla wypisuje aktualne wpisy i pyta o akcję. Add/Edit/
  Delete modyfikują słownik w pamięci i **natychmiast** zapisują
  (`json.dumps(..., indent=2)`) całość z powrotem do pliku. `Continue`
  kończy pętlę i zwraca aktualny słownik.
- `prompt_output_directory(default_output: Path) -> Path` — pyta
  (`questionary.confirm`) czy użyć domyślnej ścieżki; jeśli nie, otwiera
  `browse_for_directory` zaczynając od katalogu nadrzędnego domyślnej
  ścieżki.
- `run_interactive_mode() -> None` — orkiestruje powyższe kroki w
  kolejności opisanej w sekcji Architektura, kończąc wywołaniem
  `run_anonymization`.
- `run_anonymization(source_dir: Path, replacements_file: Path,
  output_root: Path) -> None` — wydzielona z obecnego `main()` logika
  skanowania/przetwarzania/podsumowania, bez zmian w zachowaniu względem
  dzisiejszego CLI.

Wszystkie funkcje `browse_*`/`manage_*`/`prompt_*` przy otrzymaniu `None`
z `.ask()` (Ctrl-C) rzucają `KeyboardInterrupt`, przechwytywany raz, na
najwyższym poziomie `run_interactive_mode()`, drukujący `"Anulowano."` i
kończący funkcję bez tracebacku.

## Zależności

Nowy pakiet pip: `questionary`, dopisany do `requirements.txt`. Import
miękki (`try/except ImportError`) wewnątrz `run_interactive_mode()` (nie
na poziomie modułu) — dzięki temu klasyczny tryb CLI z argumentami
działa nawet bez zainstalowanego `questionary`, identycznie jak dziś
PDF/OCR działają niezależnie od tego czy zainstalowane jest `pymupdf`.

## Testowanie

Testy jednostkowe mockujące `questionary.select`, `questionary.text`,
`questionary.confirm` (podmiana na funkcje zwracające zaprogramowaną
sekwencję odpowiedzi), weryfikujące:

- `manage_replacements_dictionary`: dodanie wpisu zapisuje go do pliku
  natychmiast; edycja zmienia wartość i zapisuje; usunięcie usuwa wpis i
  zapisuje; `Continue` zwraca aktualny stan słownika.
- `browse_for_directory`: wybór `..` przechodzi do katalogu nadrzędnego;
  wybór podfolderu wchodzi w niego; `[Wybierz ten folder]` zwraca
  bieżącą ścieżkę.
- `browse_for_replacements_file`: wybór istniejącego `.json` zwraca jego
  ścieżkę; opcja "utwórz nowy" tworzy pusty plik i zwraca jego ścieżkę.
- Ctrl-C (mock zwraca `None`) w dowolnym kroku powoduje czyste
  zakończenie z komunikatem "Anulowano.", bez wyjątku wyciekającego na
  zewnątrz.
- `run_anonymization` wydzielona z `main()`: test regresyjny potwierdzający,
  że klasyczny CLI (z argumentami) nadal daje identyczny wynik jak przed
  refaktoryzacją (uruchomienie na tym samym drzewku źródłowym co istniejące
  testy integracyjne `main()`/CLI).
