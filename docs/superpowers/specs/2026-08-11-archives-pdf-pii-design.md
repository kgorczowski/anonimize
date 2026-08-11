# Rozszerzenie anonymize.py: archiwa, PDF -> Markdown, detekcja PII

Data: 2026-08-11
Status: zatwierdzony

## Kontekst

`anonymize.py` to skrypt CLI, który rekurencyjnie skanuje katalog źródłowy,
anonimizuje pliki tekstowe/kodowe przez podstawienie ciągów znaków ze
słownika (`replacements.json`), a pliki Office (docx/xlsx/pptx) konwertuje
do Markdown przed anonimizacją. Działa dwuetapowo: najpierw skan (żeby znać
dokładną liczbę plików i pokazywać wiarygodny pasek postępu z ETA), potem
przetwarzanie.

## Cel

Rozszerzyć skrypt o:
1. Obsługę archiwów (zip i inne) — rozpakowanie i przepuszczenie zawartości
   przez istniejący pipeline anonimizacji.
2. Konwersję PDF -> Markdown, analogiczną do istniejących konwerterów
   docx/xlsx/pptx, z obsługą skanów (OCR).
3. Dodatkową, automatyczną anonimizację danych osobowych (PII) wykrywanych
   wzorcami (regex), niezależną od słownika w `replacements.json`.

## Zakres

### W zakresie

- Formaty archiwów: `.zip`, `.tar`, `.tar.gz`/`.tgz`, `.tar.bz2`/`.tbz2`,
  `.tar.xz`/`.txz`, `.7z`, `.rar`.
- Archiwa są rozpakowywane, ich zawartość przechodzi pełny pipeline
  (w tym rekurencyjnie kolejne archiwa, konwersję Office/PDF, anonimizację
  słownikową i PII). Wynik zostaje jako zwykły folder w katalogu wyjściowym
  — bez ponownego pakowania.
- Konwersja PDF -> Markdown: tekst wprost tam gdzie PDF ma warstwę tekstową,
  z automatycznym fallbackiem na OCR (Tesseract) dla stron będących
  zeskanowanymi obrazami. Podstawowe tabele wykrywane i emitowane jako
  tabele Markdown.
- Detekcja PII przez wzorce (regex), zawsze włączona, działająca na tych
  samych plikach co dzisiejsza anonimizacja słownikowa (tekst/kod +
  skonwertowane docx/xlsx/pptx/pdf), uruchamiana **po** anonimizacji
  słownikowej. Kategorie: e-mail, telefon, PESEL, NIP, IBAN, numer karty
  płatniczej, adres IPv4. Każda kategoria ma własny generyczny placeholder
  (`[EMAIL]`, `[PHONE]`, `[PESEL]`, `[NIP]`, `[IBAN]`, `[CARD]`, `[IP]`).
  PESEL, NIP, IBAN i numer karty są dodatkowo walidowane sumą kontrolną
  (odpowiednio: algorytm PESEL, algorytm NIP, mod-97, Luhn), żeby nie
  oznaczać przypadkowych ciągów cyfr jako PII.
- Błędy per-archiwum/per-plik nie przerywają całego przebiegu: są logowane,
  liczone w podsumowaniu, a plik/archiwum którego nie udało się przetworzyć
  jest kopiowany bez zmian — zgodnie z dzisiejszą filozofią obsługi błędów.
- Nowe zależności pip są ładowane przez miękki `try/except ImportError` z
  czytelnym komunikatem instalacyjnym, tak jak dziś dla
  `python-docx`/`openpyxl`/`python-pptx`. Dodany zostaje `requirements.txt`.
- Podsumowanie końcowe zyskuje liczniki: archiwa rozpakowane, PDF ->
  Markdown (osobno od Office -> Markdown), fragmenty PII zamaskowane.
- Cały nowy kod zostaje w jednym pliku `anonymize.py` (świadoma decyzja —
  nie dzielimy na moduły).

### Poza zakresem (świadomie pominięte)

- Ponowne pakowanie przetworzonej zawartości archiwum z powrotem do zip/tar
  — wynik zostaje jako folder.
- Dopasowanie bez uwzględniania wielkości liter lub na granicach słów dla
  wpisów w `replacements.json` — zachowanie tego mechanizmu bez zmian.
- Flaga CLI do włączania/wyłączania detekcji PII — zawsze włączona, bez
  nowej opcji.
- Numerowane/spójne placeholdery PII (np. `[EMAIL_1]`, `[EMAIL_2]`) —
  używamy generycznych placeholderów per typ.
- REGON, adresy IPv6, wykrywanie nazwisk (NER) — nie wchodzą w zakres tej
  iteracji.
- Zabezpieczenie przed zip-bombami / limitami rozmiaru rozpakowanej
  zawartości — narzędzie lokalne, uruchamiane przez użytkownika na
  własnych plikach, więc nie jest to traktowane jako granica zaufania.
- Nowe flagi CLI dla głębokości rekursji archiwów — wartość domyślna
  zaszyta w kodzie (10 poziomów zagnieżdżenia).

## Architektura

Model dwuetapowy (skan -> przetwarzanie) zostaje zachowany, ale etap skanu
robi więcej pracy:

1. **Skan.** `scan_files` rekurencyjnie przechodzi `source_dir` jak dziś.
   Gdy natrafi na plik z rozszerzeniem archiwum, rozpakowuje je do nowego
   katalogu tymczasowego (`tempfile.mkdtemp()`), po czym rekurencyjnie
   skanuje ten katalog tym samym mechanizmem — więc zagnieżdżone archiwum
   w archiwum rozpakowuje się samo, aż do limitu głębokości (10). Wynikiem
   skanu jest lista rekordów `(rzeczywista_ścieżka_źródłowa,
   docelowa_ścieżka_względna)` zamiast płaskiej listy ścieżek — bo pliki
   pochodzące z archiwum fizycznie leżą w katalogu tymczasowym, a ich
   docelowa ścieżka względna musi odzwierciedlać strukturę
   `<oryginalny_katalog>/<nazwa_archiwum_bez_rozszerzenia>/<ścieżka_w_archiwum>`.
2. **Przetwarzanie.** Bez zmian koncepcyjnych względem dziś: dla każdego
   rekordu dispatch po rozszerzeniu pliku (tekst/kod, docx, xlsx, pptx,
   pdf, nieznany/binarny), z dwoma nowymi gałęziami (PDF, oraz PII jako
   dodatkowy krok po anonimizacji słownikowej dla tekstu/kodu i wszystkich
   konwersji do Markdown).
3. **Sprzątanie.** Wszystkie katalogi tymczasowe utworzone podczas
   rozpakowywania archiwów są usuwane na końcu przebiegu, w bloku
   `try/finally` obejmującym skan i przetwarzanie — również gdy coś
   rzuci wyjątkiem w trakcie.

## Szczegóły komponentów

### Obsługa archiwów

Nowy zbiór `ARCHIVE_EXTENSIONS` oraz funkcja `extract_archive(path,
dest_dir)`, dispatch po rozszerzeniu:

| Rozszerzenie | Biblioteka | Zależność systemowa |
|---|---|---|
| `.zip` | `zipfile` (stdlib) | brak |
| `.tar`, `.tar.gz`/`.tgz`, `.tar.bz2`/`.tbz2`, `.tar.xz`/`.txz` | `tarfile` (stdlib) | brak |
| `.7z` | `py7zr` (pip) | brak |
| `.rar` | `rarfile` (pip) | `unrar`/`unar`/`bsdtar` w PATH |

Błąd rozpakowania (uszkodzone archiwum, hasło, brak narzędzia systemowego
dla RAR) jest łapany, logowany jak dzisiejsze błędy per-plik, a archiwum
jest kopiowane bez zmian do wyjścia zamiast przerywać cały przebieg.
Ten sam fallback (kopia bez zmian + wpis w logu) obowiązuje, gdy
archiwum zagnieżdżone przekroczy limit głębokości (10) — dalsze
rozpakowywanie na tym poziomie się zatrzymuje, a napotkane archiwum
trafia do wyjścia jako plik, nieprzetworzone.

Nazewnictwo wyjścia: `raport.zip` -> folder `raport/` w tej samej
lokalizacji względnej, zawierający przetworzoną (zanonimizowaną,
skonwertowaną) zawartość — archiwum jako plik znika z wyjścia, tak jak
dziś `raport.docx` znika na rzecz `raport.md`. Zasada stosuje się
rekurencyjnie: archiwum `inner.zip` zagnieżdżone wewnątrz `outer.zip`
trafia do `outer/inner/...`, czyli każdy poziom rozpakowania dokłada
kolejny segment ścieżki.

### Konwersja PDF -> Markdown

Nowa funkcja `convert_pdf_to_markdown(source)`, wzorowana na istniejących
`convert_docx_to_markdown` / `convert_xlsx_to_markdown` /
`convert_pptx_to_markdown`. Używa **PyMuPDF** (pakiet `pymupdf`, import
`fitz`):

- Dla każdej strony: `page.get_text()`. Jeśli wynik jest pusty/samo
  białe znaki (heurystyka: mniej niż ~10 znaków po `strip()`) -> strona
  jest traktowana jako skan -> renderowana do obrazu przez
  `page.get_pixmap()` -> tekst wyciągany przez `pytesseract.image_to_string()`.
- Strony rozdzielone nagłówkiem `# Page N`, spójnie ze stylem `# Slide N`
  w `convert_pptx_to_markdown`.
- Podstawowe tabele wykrywane przez `page.find_tables()` (jeśli dostępne)
  i emitowane jako tabele Markdown, analogicznie do tabel w
  docx/xlsx.
- Brak silnika Tesseract w systemie -> `pytesseract` rzuca błąd przy
  pierwszej próbie OCR -> łapany i re-raised jako `RuntimeError` z
  czytelną instrukcją instalacji (Windows: `winget install
  UB-Mannheim.TesseractOCR`), zgodnie z istniejącym wzorcem komunikatów
  o brakujących zależnościach (`Missing python-docx. Install it with:
  ...`).

Wynik konwersji przechodzi przez `anonymize_text` (słownik), a następnie
`redact_pii`, tak samo jak dziś dla docx/xlsx/pptx, i zapisywany jest z
rozszerzeniem `.md`.

### Detekcja PII

Nowa funkcja `redact_pii(text: str) -> str`, wywoływana bezpośrednio po
`anonymize_text` dla: plików tekstowych/kodowych oraz wyniku konwersji
docx/xlsx/pptx/pdf. Nie dotyczy plików kopiowanych bez zmian
(nieznane/binarne).

Kategorie i placeholdery:

| Kategoria | Placeholder | Walidacja |
|---|---|---|
| E-mail | `[EMAIL]` | format |
| Telefon | `[PHONE]` | format (PL + ogólny) |
| PESEL | `[PESEL]` | suma kontrolna PESEL |
| NIP | `[NIP]` | suma kontrolna NIP |
| IBAN | `[IBAN]` | mod-97 |
| Numer karty płatniczej | `[CARD]` | Luhn |
| Adres IPv4 | `[IP]` | zakres oktetów 0-255 |

Detekcja regexowa jest z natury heurystyczna: może sporadycznie nie złapać
nietypowego formatu albo (rzadko, dzięki walidacji sumami kontrolnymi)
oznaczyć coś co PII nie jest. To świadomie zaakceptowane ograniczenie
podejścia, nie błąd do wyeliminowania w tej iteracji.

### Zależności

Nowe pakiety pip: `py7zr`, `rarfile`, `pymupdf`, `pytesseract`, `Pillow`.
Zapisane w nowym `requirements.txt`. Każdy importowany miękko
(`try/except ImportError`) w miejscu użycia, z komunikatem instalacyjnym —
tak jak dziś dla `python-docx`/`openpyxl`/`python-pptx`.

Zależności systemowe (poza `pip install`):
- `unrar` (lub `unar`/`bsdtar`) w PATH — wymagane tylko dla plików `.rar`.
- Silnik `Tesseract OCR` w systemie — wymagany tylko dla PDF-ów będących
  skanami.

Brak zależności systemowej degraduje tylko odpowiednią funkcję (błąd +
kopia bez zmian dla archiwum RAR; czytelny `RuntimeError` dla PDF-a
wymagającego OCR), nie wywala całego skryptu.

### Raportowanie i błędy

Filozofia błędów zostaje identyczna jak dziś: wyjątek per-plik/archiwum
jest łapany, logowany na `stderr`, liczony w `errors`, przebieg leci
dalej. Podsumowanie końcowe zyskuje nowe liczniki obok istniejących
(`Text/code`, `Office -> Markdown`, `Copied unchanged`, `Errors`):

- `Archiwa rozpakowane`
- `PDF -> Markdown` (osobno od `Office -> Markdown`)
- `Fragmenty PII zamaskowane`

### CLI

Bez zmian względem dziś: `source`, `replacements`, `--output`. Detekcja
PII zawsze włączona, bez nowej flagi. Głębokość rekursji archiwów to stała
w kodzie (10), bez nowej flagi.

## Testowanie

Podejście TDD tam, gdzie to praktyczne:
- Testy jednostkowe dla walidacji sum kontrolnych PII (PESEL, NIP, mod-97
  IBAN, Luhn) — czysta logika, testowalna bez plików na dysku.
- Testy na małych plikach fixture: przykładowy `.zip` z plikiem tekstowym
  w środku (w tym wariant z zagnieżdżonym archiwum), mały PDF z warstwą
  tekstową, mały PDF-skan (obraz bez warstwy tekstowej) do ścieżki OCR.
- Testy na przykładowych stringach PII (poprawne i niepoprawne sumy
  kontrolne) żeby potwierdzić że fałszywe trafienia są odrzucane.

Dokładny podział na przypadki testowe i kolejność ich pisania zostanie
rozpisany w planie implementacji.
