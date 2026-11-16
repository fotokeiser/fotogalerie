# Fotogalerie

Professionelle Online-Galerie für Kundenfotos – im Stil von Pixieset/Squarespace:
Vollbild-Cover, Bildraster ohne Beschnitt, Lightbox, Favoriten, Download einzelner
Bilder und „Alle herunterladen“ als ZIP-Pakete.

## Wie das aufgebaut ist

| Teil | Wo | Warum |
|---|---|---|
| Website + Vorschaubilder (≈ 0,5 MB/Foto) | GitHub-Repo → **Cloudflare Pages** | kostenlos, schnell, auch mit privatem Repo |
| Originale + ZIPs (deine 8,5 GB) | **Cloudflare R2** | 10 GB gratis, danach 0,015 $/GB/Monat, **Downloads kostenlos** |

**Warum nicht alles auf GitHub?** GitHub erlaubt max. 100 MB pro Datei und empfiehlt
höchstens 1 GB pro Repo bzw. GitHub-Pages-Seite. 8,5 GB Originale passen da nicht rein.
Außerdem müsste das Repo für kostenloses GitHub Pages öffentlich sein – dann könnte jeder
die Kundenfotos im Repo sehen.

## Einmalige Einrichtung

### 1. Eigene Daten eintragen
`site.config.json` öffnen und Name, Website, E-Mail, Instagram eintragen.

### 2. Cloudflare R2 (Speicher für die Originale)
1. Konto auf cloudflare.com anlegen → **R2** aktivieren (Cloudflare verlangt dafür eine
   Zahlungsmethode, auch im Gratis-Kontingent).
2. Bucket anlegen, z. B. `fotogalerie`.
3. Bucket → *Settings* → *Custom Domains* → z. B. `downloads.deinedomain.de` verbinden
   (geht, wenn deine Domain bei Cloudflare liegt). Notlösung ohne Domain: „r2.dev“-Adresse
   aktivieren – die ist aber gedrosselt und nur zum Testen gedacht.
4. R2 → *Manage API Tokens* → Token mit **Object Read & Write** für den Bucket erstellen.
   Notiere Access Key ID, Secret Access Key und deine Account-ID.
5. rclone installieren und verbinden (Werte aus Schritt 4 einsetzen):

```bash
brew install rclone
```

```bash
rclone config create r2 s3 provider=Cloudflare access_key_id=DEIN_KEY secret_access_key=DEIN_SECRET endpoint=https://DEINE_ACCOUNT_ID.r2.cloudflarestorage.com acl=private no_check_bucket=true
```

6. In `site.config.json` eintragen:
   - `"downloadBaseUrl": "https://downloads.deinedomain.de"`
   - `"rcloneRemote": "r2:fotogalerie"`

> Solange `downloadBaseUrl` leer ist, laden Kunden die 2400-px-Vorschauversion herunter
> (praktisch zum Testen).

### 3. GitHub + Cloudflare Pages (die Website)
1. Auf GitHub ein **privates** Repository anlegen und diesen Ordner hochladen.
2. Cloudflare → *Workers & Pages* → *Create* → *Pages* → *Connect to Git* → Repo wählen.
3. Build-Einstellungen: **Build command leer lassen**, **Output directory: `docs`**.
4. Optional eigene Domain verbinden, z. B. `galerie.deinedomain.de`.

Ab jetzt geht jede Änderung, die du zu GitHub pushst, automatisch online.

## Neue Galerie veröffentlichen

```bash
python3 build.py new anna-ben-k7x2
```

Dann `galleries/anna-ben-k7x2/gallery.json` ausfüllen:

```json
{
  "title": "Anna & Ben",
  "subtitle": "Hochzeit",
  "date": "2026-09-12",
  "source": "~/Pictures/Export/Anna-Ben",
  "cover": "IMG_0412.jpg",
  "coverPosition": "center 40%",
  "allowDownload": true,
  "listed": false
}
```

- **source**: Ordner mit den fertig exportierten JPEGs. **Unterordner werden zu Kapiteln**
  (z. B. `01 Getting Ready`, `02 Trauung`, `03 Feier` – die Nummer bestimmt die Reihenfolge
  und wird nicht angezeigt).
- **cover**: Dateiname des Titelbilds (leer = erstes Foto). `coverPosition` verschiebt den Ausschnitt.
- **listed**: `true` = erscheint auf der Startseite. Für Kundengalerien `false` lassen –
  dann kennt nur, wer den Link hat, die Galerie. Ein zufälliges Kürzel im Namen
  (`anna-ben-k7x2`) macht den Link unratbar.

Dann:

```bash
python3 build.py zip anna-ben-k7x2
```

```bash
python3 build.py upload anna-ben-k7x2
```

```bash
python3 build.py build
```

```bash
git add -A && git commit -m "Galerie Anna & Ben" && git push
```

Die Galerie ist danach unter `https://galerie.deinedomain.de/anna-ben-k7x2/` erreichbar.

- `zip` packt die Originale in Pakete à max. 2 GB (`zipPartMaxGB`) – große Einzel-ZIPs
  brechen bei Kunden gern ab. Ohne `zip` gibt es kein Paket, Kunden können dann alle Fotos
  einzeln laden.
- `upload` lädt Originale + ZIPs zu R2 hoch und setzt dabei den Header
  `Content-Disposition: attachment`, damit ein Klick wirklich herunterlädt statt das Bild zu öffnen.
- `build` ist schnell, wenn schon gebaut wurde – nur neue/geänderte Fotos werden neu verkleinert.

## Was die Galerie kann

- Vollbild-Titelbild mit Name, Anlass und Datum
- Bildraster im „Justified“-Stil (alle Fotos unbeschnitten, Zeilen bündig), Lazy Loading
- Kapitel-Navigation in der Leiste
- Lightbox: Pfeiltasten, Wischen am Handy, `F` = Favorit, `D` = Download, `Esc` = schließen,
  jedes Bild hat einen eigenen Link
- Favoriten (werden im Browser des Kunden gespeichert) → herunterladen, per E-Mail an dich
  schicken oder Dateiliste kopieren – ideal für Album-Auswahl
- „Herunterladen“: ZIP-Pakete, alle einzeln oder nur Favoriten
- Galerien sind für Suchmaschinen gesperrt (`noindex`)

## Passwortschutz (optional)

Eine statische Seite kann kein echtes Passwort prüfen. Wer das braucht: Cloudflare
*Zero Trust* → *Access* → Anwendung für `galerie.deinedomain.de/anna-ben-k7x2/*` anlegen,
Regel „E-Mail ist kunde@…“. Der Kunde bekommt dann einen Einmal-Code per Mail
(kostenlos bis 50 Nutzer).

## Kosten bei 8,5 GB

- Originale 8,5 GB + ZIPs 8,5 GB = 17 GB → 7 GB über dem Gratis-Kontingent ≈ **0,11 $ pro Monat**
- Downloads (Traffic) bei R2: **kostenlos**
- Cloudflare Pages + privates GitHub-Repo: **kostenlos**

## Anpassen

- Farben/Schriften: `template/assets/style.css` (Variablen ganz oben)
- Aufbau der Seite: `template/gallery.html`
- Verhalten: `template/assets/gallery.js`
- Bildgrößen/Qualität: `previewSize`, `thumbSize`, `quality` in `site.config.json`

Nach Änderungen immer `python3 build.py build` ausführen. Lokal ansehen:

```bash
python3 -m http.server 8000 -d docs
```

→ http://localhost:8000

Voraussetzung: macOS (nutzt das eingebaute `sips` zum Verkleinern) und Python 3.
