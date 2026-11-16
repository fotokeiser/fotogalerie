#!/usr/bin/env python3
"""
Fotogalerie – Build-Werkzeug (macOS, keine Zusatzpakete nötig)

  python3 build.py build            Vorschaubilder erzeugen + Website nach docs/ bauen
  python3 build.py zip <galerie>    Originale als ZIP-Pakete (für "Alle herunterladen") packen
  python3 build.py upload <galerie> Originale + ZIPs mit rclone zu Cloudflare R2 hochladen
  python3 build.py new <galerie>    Neue Galerie-Konfiguration anlegen

Nutzt das in macOS eingebaute `sips` zum Verkleinern der Bilder.
"""
import argparse
import concurrent.futures as cf
import html
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import urllib.parse
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "template"
GALLERIES = ROOT / "galleries"
DOWNLOADS = ROOT / "downloads"
EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".heic", ".webp"}
SRGB = "/System/Library/ColorSync/Profiles/sRGB Profile.icc"
MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
          "August", "September", "Oktober", "November", "Dezember"]
ROTATE = {3: 180, 6: 90, 8: 270}
WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


# ---------------------------------------------------------------- helpers
def load_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def site_config():
    return load_json(ROOT / "site.config.json")


def all_galleries():
    if not GALLERIES.exists():
        return []
    out = []
    for d in sorted(GALLERIES.iterdir()):
        cfg = d / "gallery.json"
        if cfg.exists():
            g = load_json(cfg)
            g["slug"] = d.name
            out.append(g)
    return out


def get_gallery(slug):
    for g in all_galleries():
        if g["slug"] == slug:
            return g
    sys.exit(f"Galerie '{slug}' nicht gefunden (erwartet: galleries/{slug}/gallery.json)")


def safe_name(s):
    return re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-") or "bild"


def human_date(s):
    try:
        d = date.fromisoformat(s)
        return f"{d.day}. {MONTHS[d.month - 1]} {d.year}"
    except (TypeError, ValueError):
        return s or ""


def url_join(base, *parts):
    path = "/".join(urllib.parse.quote(p) for part in parts for p in str(part).split("/") if p)
    return base.rstrip("/") + "/" + path


def sips_info(path):
    r = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", "-g", "orientation", str(path)],
                       capture_output=True, text=True)
    info = {}
    for line in r.stdout.splitlines():
        m = re.match(r"\s+(\w+):\s*(\S+)", line)
        if m:
            info[m.group(1)] = m.group(2)
    w, h = int(info.get("pixelWidth", 0)), int(info.get("pixelHeight", 0))
    o = int(info["orientation"]) if info.get("orientation", "").isdigit() else 1
    return w, h, o


def scan_source(source, group_by=None):
    """Bilder im Hauptordner = ein Set ohne Titel; jeder Unterordner = eigenes Set."""
    src = Path(os.path.expanduser(source))
    if not src.is_dir():
        sys.exit(f"Quellordner nicht gefunden: {src}")

    def images_in(d):
        return sorted((p for p in d.iterdir()
                       if p.is_file() and not p.name.startswith(".") and p.suffix.lower() in EXTS),
                      key=lambda p: natural_key(p.name))

    sets = []
    root_imgs = images_in(src)
    if root_imgs:
        sets.append({"name": "", "dir": "", "files": root_imgs})
    for d in sorted((d for d in src.iterdir() if d.is_dir() and not d.name.startswith(".")),
                    key=lambda d: natural_key(d.name)):
        imgs = images_in(d)
        if imgs:
            name = re.sub(r"^\d+[\s._-]*", "", d.name) or d.name
            sets.append({"name": name, "dir": d.name, "files": imgs})

    # Ohne Unterordner optional nach Aufnahmetag (EXIF) in Kapitel aufteilen
    if group_by == "day" and len(sets) == 1 and not sets[0]["dir"]:
        by_day = {}
        for f in sets[0]["files"]:
            by_day.setdefault((exif_date(f) or "")[:10], []).append(f)
        if len(by_day) > 1:
            sets = [{"name": day_label(day), "dir": "", "files": files}
                    for day, files in sorted(by_day.items(), key=lambda kv: kv[0] or "9999")]
    return src, sets


def natural_key(s):
    """'Bild-2' vor 'Bild-10' sortieren."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def exif_date(path):
    """Aufnahmedatum (DateTimeOriginal) als 'JJJJ:MM:TT hh:mm:ss' aus dem JPEG-EXIF lesen."""
    try:
        with open(path, "rb") as fh:
            data = fh.read(262144)
        i = data.find(b"Exif\x00\x00")
        if i < 0:
            return None
        t = data[i + 6:]
        e = "<" if t[:2] == b"II" else ">"
        u16 = lambda o: struct.unpack_from(e + "H", t, o)[0]
        u32 = lambda o: struct.unpack_from(e + "I", t, o)[0]

        def ifd(off):
            return {u16(off + 2 + 12 * k): off + 2 + 12 * k for k in range(u16(off))}

        ifd0 = ifd(u32(4))
        if 0x8769 not in ifd0:
            return None
        sub = ifd(u32(ifd0[0x8769] + 8))
        for tag in (0x9003, 0x9004):
            if tag in sub:
                off = u32(sub[tag] + 8)
                return t[off:off + 19].decode("ascii")
    except (OSError, struct.error, UnicodeDecodeError):
        return None
    return None


def day_label(day):
    try:
        d = date(int(day[:4]), int(day[5:7]), int(day[8:10]))
    except ValueError:
        return "Weitere Fotos"
    return f"{WEEKDAYS[d.weekday()]}, {d.day}. {MONTHS[d.month - 1]}"


def make_resized(src, dst, size, quality):
    """Erzeugt eine sRGB-JPEG-Version mit max. `size` px Kantenlänge. Gibt (w, h) zurück."""
    if not (dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime):
        dst.parent.mkdir(parents=True, exist_ok=True)
        sw, sh, so = sips_info(src)
        tmp = dst.with_name(dst.stem + ".tmp.jpg")
        cmd = ["sips", "-s", "format", "jpeg", "-s", "formatOptions", str(quality)]
        if os.path.exists(SRGB):
            cmd += ["-m", SRGB]
        if max(sw, sh) > size:
            cmd += ["-Z", str(size)]
        cmd += [str(src), "--out", str(tmp)]
        subprocess.run(cmd, check=True, capture_output=True)
        # Falls sips die EXIF-Drehung verworfen hat: Pixel selbst drehen
        _, _, do = sips_info(tmp)
        if so in ROTATE and do == 1:
            subprocess.run(["sips", "-r", str(ROTATE[so]), str(tmp)], check=True, capture_output=True)
        os.replace(tmp, dst)
    w, h, o = sips_info(dst)
    if o in (5, 6, 7, 8):
        w, h = h, w
    return w, h


def download_base(site):
    """Basis-URL der Originale: GitHub-Releases (githubRepo) oder eigener Speicher (downloadBaseUrl)."""
    if site.get("githubRepo"):
        return f"https://github.com/{site['githubRepo']}/releases/download"
    return (site.get("downloadBaseUrl") or "").strip()


def asset_name(rel):
    """GitHub-Releases kennen keine Unterordner: 'Kapitel/Bild.jpg' → 'Kapitel-Bild.jpg'."""
    return safe_name(rel.replace("/", "-"))


def human_size(n):
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024 or unit == "GB":
            return (f"{n:.1f} {unit}" if unit in ("MB", "GB") else f"{int(n)} {unit}").replace(".", ",")
        n /= 1024


# ---------------------------------------------------------------- build
def build_gallery(g, site, out_root, pool):
    slug = g["slug"]
    src_root, sets = scan_source(g["source"], g.get("groupBy"))
    out = out_root / slug
    out.mkdir(parents=True, exist_ok=True)
    base = download_base(site)
    on_github = bool(site.get("githubRepo"))
    allow_dl = g.get("allowDownload", True)

    jobs, used = [], set()
    for s in sets:
        for f in s["files"]:
            rel = f"{s['dir']}/{f.name}" if s["dir"] else f.name
            name = safe_name(f"{s['dir']}-{f.stem}" if s["dir"] else f.stem)
            while name in used:
                name += "-1"
            used.add(name)
            t = out / "t" / f"{name}.jpg"
            p = out / "p" / f"{name}.jpg"
            jobs.append((s, f, rel, name,
                         pool.submit(make_resized, f, t, site.get("thumbSize", 1200), site.get("quality", 82)),
                         pool.submit(make_resized, f, p, site.get("previewSize", 2400), site.get("quality", 82))))

    total = len(jobs)
    data_sets = {id(s): {"name": s["name"], "images": []} for s in sets}
    cover = None
    for i, (s, f, rel, name, tj, pj) in enumerate(jobs, 1):
        tw, th = tj.result()
        pj.result()
        print(f"\r  {slug}: {i}/{total} Bilder", end="", flush=True)
        img = {
            "id": name,
            "name": f.name,
            "t": f"t/{name}.jpg",
            "p": f"p/{name}.jpg",
            "w": tw, "h": th,
            "size": f.stat().st_size,
        }
        if allow_dl:
            if on_github:
                img["dl"] = url_join(base, slug, asset_name(rel))
            else:
                img["dl"] = url_join(base, slug, rel) if base else f"p/{name}.jpg"
        data_sets[id(s)]["images"].append(img)
        if cover is None or g.get("cover") in (f.name, rel):
            cover = img
    print()

    # Alte Vorschaubilder entfernen, die nicht mehr im Quellordner sind
    for sub in ("t", "p"):
        for old in (out / sub).glob("*.jpg"):
            if old.stem not in used:
                old.unlink()

    zips = []
    if allow_dl and base:
        for z in sorted((DOWNLOADS / slug).glob("*.zip")):
            zip_url = url_join(base, slug, z.name) if on_github else url_join(base, slug, "_zip", z.name)
            zips.append({"name": z.name, "url": zip_url,
                         "size": z.stat().st_size, "sizeText": human_size(z.stat().st_size)})

    data = {
        "slug": slug,
        "title": g.get("title", slug),
        "subtitle": g.get("subtitle", ""),
        "date": human_date(g.get("date", "")),
        "photographer": site.get("photographer", ""),
        "email": site.get("email", ""),
        "download": bool(allow_dl),
        "originals": bool(base),
        "zips": zips,
        "sets": [data_sets[id(s)] for s in sets],
    }
    count = sum(len(s["images"]) for s in data["sets"])

    tpl = (TEMPLATE / "gallery.html").read_text(encoding="utf-8")
    cover_url = cover["p"] if cover else ""
    og = (site.get("siteUrl", "").rstrip("/") + f"/{slug}/{cover_url}") if site.get("siteUrl") else cover_url
    page = fill(tpl, site, {
        "TITLE": data["title"],
        "SUBTITLE": data["subtitle"],
        "DATE": data["date"],
        "COVER": cover_url,
        "COVER_POS": g.get("coverPosition", "center 40%"),
        "OG_IMAGE": og,
        "COUNT": f"{count} Fotos",
    })
    page = page.replace("{{DATA}}", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    (out / "index.html").write_text(page, encoding="utf-8")
    return {"slug": slug, "title": data["title"], "subtitle": data["subtitle"], "date": data["date"],
            "cover": f"{slug}/{cover['t']}" if cover else "", "count": count, "listed": g.get("listed", False)}


def fill(tpl, site, values):
    links = []
    if site.get("website"):
        label = re.sub(r"^https?://(www\.)?", "", site["website"]).rstrip("/")
        links.append(f'<a href="{html.escape(site["website"])}">{html.escape(label)}</a>')
    if site.get("email"):
        links.append(f'<a href="mailto:{html.escape(site["email"])}">{html.escape(site["email"])}</a>')
    if site.get("instagram"):
        handle = site["instagram"].lstrip("@")
        links.append(f'<a href="https://instagram.com/{html.escape(handle)}">@{html.escape(handle)}</a>')
    values = {
        "PHOTOGRAPHER": site.get("photographer", ""),
        "TAGLINE": site.get("tagline", ""),
        "YEAR": str(date.today().year),
        **values,
    }
    for k, v in values.items():
        tpl = tpl.replace("{{" + k + "}}", html.escape(str(v)))
    return tpl.replace("{{FOOTER_LINKS}}", " <span>·</span> ".join(links))


def cmd_build(args):
    site = site_config()
    out_root = ROOT / site.get("outputDir", "docs")
    out_root.mkdir(exist_ok=True)
    galleries = all_galleries()
    if args.only:
        galleries = [g for g in galleries if g["slug"] in args.only]
    if not galleries:
        print("Keine Galerien gefunden. Lege eine an mit:  python3 build.py new <name>")
    # Assets kopieren
    if (out_root / "assets").exists():
        shutil.rmtree(out_root / "assets")
    shutil.copytree(TEMPLATE / "assets", out_root / "assets")
    (out_root / ".nojekyll").write_text("")

    summaries = []
    with cf.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        for g in galleries:
            src = Path(os.path.expanduser(g.get("source", "")))
            if not g.get("source") or not src.is_dir():
                print(f"  ⚠ {g['slug']}: übersprungen – Fotoordner nicht gefunden: {src}\n"
                      f"    → in galleries/{g['slug']}/gallery.json bei \"source\" den Ordner mit den Fotos eintragen.")
                continue
            summaries.append(build_gallery(g, site, out_root, pool))

    # Startseite: nur Galerien mit "listed": true erscheinen dort
    cards = []
    for s in summaries:
        if not s["listed"]:
            continue
        cards.append(
            f'<a class="card" href="{html.escape(s["slug"])}/">'
            f'<div class="card-img"><img src="{html.escape(s["cover"])}" alt="" loading="lazy"></div>'
            f'<p class="eyebrow">{html.escape(s["subtitle"])}</p>'
            f'<h2>{html.escape(s["title"])}</h2>'
            f'<p class="card-meta">{html.escape(s["date"])} · {s["count"]} Fotos</p></a>')
    tpl = (TEMPLATE / "index.html").read_text(encoding="utf-8")
    page = fill(tpl, site, {}).replace("{{CARDS}}", "\n".join(cards))
    (out_root / "index.html").write_text(page, encoding="utf-8")
    print(f"Fertig → {out_root.relative_to(ROOT)}/  ({len(summaries)} Galerie(n))")


# ---------------------------------------------------------------- zip
def cmd_zip(args):
    site = site_config()
    g = get_gallery(args.gallery)
    src_root, sets = scan_source(g["source"], g.get("groupBy"))
    files = [(f, f"{s['dir']}/{f.name}" if s["dir"] else f.name) for s in sets for f in s["files"]]
    limit = float(site.get("zipPartMaxGB", 2)) * 1024 ** 3
    parts, cur, cur_size = [], [], 0
    for f, arc in files:
        sz = f.stat().st_size
        if cur and cur_size + sz > limit:
            parts.append(cur)
            cur, cur_size = [], 0
        cur.append((f, arc))
        cur_size += sz
    if cur:
        parts.append(cur)

    out = DOWNLOADS / g["slug"]
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    base = safe_name(g.get("title", g["slug"]))
    for i, part in enumerate(parts, 1):
        name = f"{base}.zip" if len(parts) == 1 else f"{base}-Teil-{i}-von-{len(parts)}.zip"
        with zipfile.ZipFile(out / name, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as z:
            for j, (f, arc) in enumerate(part, 1):
                z.write(f, arc)
                print(f"\r  {name}: {j}/{len(part)}", end="", flush=True)
        print(f"  ({human_size((out / name).stat().st_size)})")
    print(f"ZIPs liegen in downloads/{g['slug']}/ – danach 'upload' und 'build' ausführen.")


# ---------------------------------------------------------------- upload
def cmd_upload(args):
    site = site_config()
    g = get_gallery(args.gallery)
    if site.get("githubRepo"):
        return upload_github(g, site)
    if not shutil.which("rclone"):
        sys.exit("rclone fehlt. Installieren mit:  brew install rclone   (Einrichtung siehe README)")
    remote = site.get("rcloneRemote", "").rstrip("/")
    if not remote:
        sys.exit("In site.config.json fehlt 'rcloneRemote' (z. B. \"r2:fotogalerie\").")
    flags = ["--header-upload", "Content-Disposition: attachment", "--exclude", ".*",
             "--progress", "--transfers", "8"]
    src = os.path.expanduser(g["source"])
    print(f"Lade Originale hoch: {src} → {remote}/{g['slug']}/")
    subprocess.run(["rclone", "copy", src, f"{remote}/{g['slug']}", *flags], check=True)
    zdir = DOWNLOADS / g["slug"]
    if zdir.exists() and any(zdir.glob("*.zip")):
        print("Lade ZIP-Pakete hoch …")
        subprocess.run(["rclone", "copy", str(zdir), f"{remote}/{g['slug']}/_zip", *flags], check=True)
    print("Upload fertig. Jetzt 'python3 build.py build' ausführen und die Website veröffentlichen.")


def upload_github(g, site):
    """Originale + ZIPs als Dateien eines GitHub-Release (Tag = Galeriename) hochladen."""
    if not shutil.which("gh"):
        sys.exit("GitHub-CLI fehlt. Installieren mit:  brew install gh   und dann:  gh auth login")
    repo, slug = site["githubRepo"], g["slug"]
    env = os.environ.copy()
    if site.get("githubAccount"):
        tok = subprocess.run(["gh", "auth", "token", "--user", site["githubAccount"]],
                             capture_output=True, text=True).stdout.strip()
        if tok:
            env["GH_TOKEN"] = tok

    def gh(*a, **kw):
        return subprocess.run(["gh", *a, "--repo", repo], env=env, **kw)

    if gh("release", "view", slug, capture_output=True).returncode != 0:
        print(f"Lege Release '{slug}' an …")
        gh("release", "create", slug, "--title", g.get("title", slug),
           "--notes", "Originaldateien der Galerie.", check=True)
    info = json.loads(gh("release", "view", slug, "--json", "assets",
                         capture_output=True, text=True, check=True).stdout)
    existing = {a["name"]: a["size"] for a in info["assets"]}

    # Was hochgeladen werden muss: neue oder geänderte Dateien
    _, sets = scan_source(g["source"], g.get("groupBy"))
    wanted = [(f, asset_name(f"{s['dir']}/{f.name}" if s["dir"] else f.name)) for s in sets for f in s["files"]]
    wanted += [(z, z.name) for z in sorted((DOWNLOADS / slug).glob("*.zip"))]
    todo = [(f, n) for f, n in wanted if existing.get(n) != f.stat().st_size]
    if len(wanted) > 1000:
        sys.exit(f"Ein GitHub-Release fasst max. 1000 Dateien – diese Galerie hat {len(wanted)}.")
    if not todo:
        print("Alles schon hochgeladen.")
        return

    # GitHub benennt die Datei nach ihrem Namen → per Verknüpfung den gewünschten Namen geben
    stage = DOWNLOADS / slug / "_upload"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    paths = []
    for f, n in todo:
        (stage / n).symlink_to(f.resolve())
        paths.append(str(stage / n))
    total = sum(f.stat().st_size for f, _ in todo)
    print(f"Lade {len(todo)} Dateien ({human_size(total)}) zu github.com/{repo}/releases/tag/{slug} hoch …")
    done = 0
    for i in range(0, len(paths), 10):
        batch = paths[i:i + 10]
        gh("release", "upload", slug, *batch, "--clobber", check=True)
        done += len(batch)
        print(f"  {done}/{len(paths)}", flush=True)
    shutil.rmtree(stage)
    print("Upload fertig. Jetzt 'python3 build.py build' ausführen und pushen.")


# ---------------------------------------------------------------- new
def cmd_new(args):
    slug = safe_name(args.gallery).lower()
    d = GALLERIES / slug
    if (d / "gallery.json").exists():
        sys.exit(f"galleries/{slug}/gallery.json existiert schon.")
    d.mkdir(parents=True, exist_ok=True)
    cfg = {
        "title": "Anna & Ben",
        "subtitle": "Hochzeit",
        "date": date.today().isoformat(),
        "source": "~/Pictures/Export/" + slug,
        "cover": "",
        "coverPosition": "center 40%",
        "allowDownload": True,
        "listed": False,
    }
    (d / "gallery.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Angelegt: galleries/{slug}/gallery.json – Titel, Datum und 'source' (Ordner mit den Fotos) anpassen.")


def main():
    ap = argparse.ArgumentParser(description="Fotogalerie bauen und veröffentlichen")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="Website bauen")
    b.add_argument("only", nargs="*", help="nur diese Galerien bauen (Standard: alle)")
    b.set_defaults(fn=cmd_build)
    for name, fn, hlp in [("zip", cmd_zip, "Originale als ZIP packen"),
                          ("upload", cmd_upload, "Originale zu R2 hochladen"),
                          ("new", cmd_new, "neue Galerie anlegen")]:
        p = sub.add_parser(name, help=hlp)
        p.add_argument("gallery")
        p.set_defaults(fn=fn)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
