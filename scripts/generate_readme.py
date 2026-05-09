"""Generate AppliTogo README from Supabase data (or local JSON fallback).

Usage:
    # From Supabase (CI / production)
    SUPABASE_URL=... SUPABASE_ANON_KEY=... python scripts/generate_readme.py

    # From a local JSON file (dev / first run)
    python scripts/generate_readme.py --json path/to/resources.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
README_PATH = REPO_ROOT / "README.md"
COUNTRY = "TG"

# Apps présentes dans l'historique du repo mais absentes de la base
# (à supprimer le jour où elles y sont ajoutées).
LEGACY_APPS = [
    {
        "name": "Nicelia", "category": "E-Commerce", "platforms": ["ANDROID"],
        "description": "Marketplace permettant de parcourir et d'acheter des produits de différentes marques.",
        "store_links": {"playstore": "https://play.google.com/store/apps/details?id=com.togo.nicelia&hl=fr"},
        "tech_links": {"website": "https://nicelia.com/"},
    },
    {
        "name": "Kiya", "category": "E-Commerce", "platforms": ["ANDROID"],
        "description": "Application d'épicerie en ligne (produits frais, légumes, viandes, poissons).",
        "store_links": {"playstore": "https://play.google.com/store/apps/details?id=com.kiyakou.app"},
        "tech_links": {},
    },
    {
        "name": "ClinicAgro", "category": "Agritech", "platforms": ["ANDROID"],
        "description": "Conseils et accompagnement agro-médical pour les acteurs agricoles.",
        "store_links": {"playstore": "https://play.google.com/store/apps/details?id=com.clinicagro"},
        "tech_links": {},
    },
    {
        "name": "Togo Tribune", "category": "MediaTech", "platforms": ["ANDROID"],
        "description": "Application d'actualité togolaise.",
        "store_links": {"playstore": "https://play.google.com/store/apps/details?id=com.actus.togotribune"},
        "tech_links": {},
    },
    {
        "name": "Melinet_tg", "category": "Fintech", "platforms": ["ANDROID"],
        "description": "Accès aux offres des opérateurs télécoms togolais via codes USSD simplifiés.",
        "store_links": {"playstore": "https://play.google.com/store/apps/details?id=com.coleta.melinettg"},
        "tech_links": {},
    },
    {
        "name": "Convertify", "category": "Autres", "platforms": ["ANDROID"],
        "description": "Convertisseur de devises avec taux de change en temps réel.",
        "store_links": {"playstore": "https://play.google.com/store/apps/details?id=com.deventhusiast.convertify"},
        "tech_links": {},
    },
]

WEB_APPS = [
    ("Chapchap", "https://chapchap.tg",
     "Livraison de plis et colis à la demande pour les professionnels."),
    ("Docmava", "https://www.docmava.com/",
     "Gestion des rendez-vous médicaux pour cabinets et praticiens."),
]

ECOMMERCE = [
    ("DuSa", "https://www.dusa.tg/",
     "Marketplace de produits locaux togolais."),
    ("Miledoo", "http://www.miledoo.net",
     "Achat-vente en ligne, création de boutiques, services à la diaspora."),
    ("Togo Informatique", "http://www.togoinformatique.com",
     "Matériels et services informatiques."),
    ("Assivito", "https://www.assivito.com/",
     "Centre commercial en ligne (du nom du Petit Marché de Lomé)."),
    ("Boenli", "https://boenli.wordpress.com/",
     "Vente d'articles high-tech."),
    ("Nicelia", "https://nicelia.com/",
     "Produits informatique, électroménager, livraison partout au Togo."),
    ("CoinAfrique", "https://tg.coinafrique.com/",
     "Petites annonces (véhicules, immobilier, mode, services)."),
    ("Assiyeyeme", "https://assiyeyeme.tg/boutique/",
     "Vente en ligne de produits artisanaux togolais."),
]

CATEGORIES = {
    "Fintech":    ("💳", "Fintech & mobile money"),
    "Mobilité":   ("🛵", "Mobilité & transport"),
    "E-Commerce": ("🛍️", "E-commerce & marketplaces"),
    "Healthtech": ("🩺", "Healthtech"),
    "Edtech":     ("📚", "Edtech"),
    "MediaTech":  ("📺", "Médias & information"),
    "FoodTech":   ("🍽️", "FoodTech"),
    "Agritech":   ("🌱", "Agritech"),
    "GovTech":    ("🏛️", "GovTech"),
    "Blockchain": ("🔗", "Blockchain"),
    "Autres":     ("✨", "Autres"),
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def fetch_from_supabase() -> list[dict]:
    """Fetch resources via the Supabase REST API (PostgREST)."""
    base = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_ANON_KEY"]
    select = (
        "name,slug,icon,cover,description,store_links,tech_links,"
        "platforms,featured,launched_at,"
        "category:categories(name),"
        "company:companies(name,logo,city)"
    )
    qs = urllib.parse.urlencode({
        "select": select,
        "country_code": f"eq.{COUNTRY}",
        "status": "eq.PUBLISHED",
        "is_approved": "eq.true",
        "order": "featured.desc,name.asc",
    })
    headers = {"apikey": key}
    # Legacy anon keys are JWTs (start with "eyJ") and need a Bearer header.
    # New publishable keys (sb_publishable_...) only need the apikey header.
    if key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(f"{base}/rest/v1/resources?{qs}", headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def load_local(path: str) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def normalize(rows: list[dict]) -> list[dict]:
    """Make seed-style and PostgREST-style rows look the same."""
    out = []
    for r in rows:
        cat = r.get("category")
        if isinstance(cat, dict):
            cat = cat.get("name")
        co = r.get("company")
        if isinstance(co, dict) and not co.get("name"):
            co = None
        out.append({
            "name":        r.get("name"),
            "slug":        r.get("slug"),
            "icon":        r.get("icon") or "",
            "description": (r.get("description") or "").strip(),
            "platforms":   r.get("platforms") or [],
            "featured":    bool(r.get("featured")),
            "store_links": r.get("store_links") or r.get("storeLinks") or {},
            "tech_links":  r.get("tech_links") or r.get("techLinks") or {},
            "category":    cat or "Autres",
            "company":     co,
        })
    return out


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def platform_badges(platforms: list[str]) -> str:
    mapping = {
        "ANDROID": "![Android](https://img.shields.io/badge/-Android-3DDC84?style=flat-square&logo=android&logoColor=white)",
        "IOS":     "![iOS](https://img.shields.io/badge/-iOS-000000?style=flat-square&logo=apple&logoColor=white)",
        "WEB":     "![Web](https://img.shields.io/badge/-Web-4285F4?style=flat-square&logo=googlechrome&logoColor=white)",
    }
    return " ".join(mapping[p] for p in platforms if p in mapping)


def app_links(a: dict) -> str:
    parts = []
    sl, tl = a["store_links"], a["tech_links"]
    if sl.get("playstore"):
        parts.append(f"[Play Store]({sl['playstore']})")
    if sl.get("appstore"):
        parts.append(f"[App Store]({sl['appstore']})")
    if tl.get("website"):
        parts.append(f"[Site]({tl['website']})")
    if tl.get("github"):
        parts.append(f"[GitHub]({tl['github']})")
    return " · ".join(parts) or "—"


def app_row(a: dict) -> str:
    icon = a["icon"]
    img = f'<img src="{icon}" width="48" alt=""/>' if icon else ""
    desc = a["description"]
    if len(desc) > 200:
        desc = desc[:197].rstrip() + "…"
    return (
        f"| {img} | **{a['name']}**<br/>"
        f"{platform_badges(a['platforms'])}<br/>"
        f"{desc}<br/>"
        f"<sub>{app_links(a)}</sub> |"
    )


def render(apps: list[dict]) -> str:
    apps = apps + normalize(LEGACY_APPS)

    by_cat: dict[str, list[dict]] = defaultdict(list)
    plat_count: dict[str, int] = defaultdict(int)
    for a in apps:
        by_cat[a["category"]].append(a)
        for p in a["platforms"]:
            plat_count[p] += 1

    total = len(apps)
    featured = [a for a in apps if a["featured"]]

    L: list[str] = []

    # ── Header ────────────────────────────────────────────────────────────
    L.append('<div align="center">')
    L.append('')
    L.append('# Appli Made in Togo 🇹🇬')
    L.append('')
    L.append("Liste communautaire des applications mobiles, sites web et plateformes en ligne conçus au Togo.")
    L.append('')
    L.append(
        f'![Apps](https://img.shields.io/badge/apps-{total}-0EA5E9?style=flat-square) '
        f'![Android](https://img.shields.io/badge/Android-{plat_count["ANDROID"]}-3DDC84?style=flat-square&logo=android&logoColor=white) '
        f'![iOS](https://img.shields.io/badge/iOS-{plat_count["IOS"]}-000000?style=flat-square&logo=apple&logoColor=white) '
        f'![Web](https://img.shields.io/badge/web-{len(WEB_APPS)+len(ECOMMERCE)}-4285F4?style=flat-square&logo=googlechrome&logoColor=white)'
    )
    L.append('')
    L.append('</div>')
    L.append('')

    # ── À la une ──────────────────────────────────────────────────────────
    if featured:
        L.append('## À la une')
        L.append('')
        L.append('<table><tr>')
        for a in featured:
            site = a["tech_links"].get("website") or a["store_links"].get("playstore") or "#"
            img = (
                f'<img src="{a["icon"]}" width="96" alt="{a["name"]}"/>'
                if a["icon"] else f'<strong>{a["name"]}</strong>'
            )
            L.append(
                f'<td align="center" width="160">'
                f'<a href="{site}">{img}</a><br/><sub>{a["category"]}</sub></td>'
            )
        L.append('</tr></table>')
        L.append('')

    # ── Applications mobiles ─────────────────────────────────────────────
    L.append('## Applications mobiles')
    L.append('')
    for cat, (emoji, label) in CATEGORIES.items():
        items = by_cat.get(cat, [])
        if not items:
            continue
        items.sort(key=lambda x: (not x["featured"], x["name"].lower()))
        L.append(f'### {emoji} {label} <sub>({len(items)})</sub>')
        L.append('')
        L.append('|     | Application |')
        L.append('| :-: | :--- |')
        for a in items:
            L.append(app_row(a))
        L.append('')

    # ── Sites web ────────────────────────────────────────────────────────
    L.append('## Applications web')
    L.append('')
    L.append('| Site | Description |')
    L.append('| :--- | :--- |')
    for name, url, desc in WEB_APPS:
        L.append(f'| [**{name}**]({url}) | {desc} |')
    L.append('')

    L.append('## Sites e-commerce')
    L.append('')
    L.append('| Site | Description |')
    L.append('| :--- | :--- |')
    for name, url, desc in ECOMMERCE:
        L.append(f'| [**{name}**]({url}) | {desc} |')
    L.append('')

    # ── Éditeurs (si companies remplies) ─────────────────────────────────
    studios: dict[str, dict] = {}
    for a in apps:
        co = a.get("company")
        if not co:
            continue
        s = studios.setdefault(co["name"], {"logo": co.get("logo"), "city": co.get("city"), "apps": []})
        s["apps"].append(a["name"])

    if studios:
        L.append('## Studios & éditeurs')
        L.append('')
        L.append('| Studio | Apps | Ville |')
        L.append('| :--- | :--- | :--- |')
        for name in sorted(studios):
            s = studios[name]
            logo = f'<img src="{s["logo"]}" width="32" alt=""/> ' if s.get("logo") else ""
            L.append(f"| {logo}**{name}** | {', '.join(s['apps'])} | {s.get('city') or '—'} |")
        L.append('')

    # ── Stats ────────────────────────────────────────────────────────────
    L.append('## Statistiques')
    L.append('')
    L.append('| Catégorie | Apps |')
    L.append('| :--- | :-: |')
    for cat, (emoji, label) in CATEGORIES.items():
        n = len(by_cat.get(cat, []))
        if n:
            L.append(f'| {emoji} {label} | {n} |')
    L.append('')
    L.append('| Plateforme | Apps |')
    L.append('| :--- | :-: |')
    for p, lab in [("ANDROID", "Android"), ("IOS", "iOS"), ("WEB", "Web")]:
        L.append(f'| {lab} | {plat_count.get(p, 0)} |')
    L.append('')

    # ── Contribuer ───────────────────────────────────────────────────────
    L.append('## Contribuer')
    L.append('')
    L.append("Une app togolaise manque à l'appel ? Deux options :")
    L.append('')
    L.append("- Ouvrir une [issue](https://github.com/gausoft/AppliTogo/issues/new) avec le lien Play Store / App Store / site.")
    L.append("- Ouvrir une Pull Request en l'ajoutant dans la bonne catégorie (voir [`CONTRIBUTING.md`](./CONTRIBUTING.md)).")
    L.append('')

    # ── Licence ──────────────────────────────────────────────────────────
    L.append('## Licence')
    L.append('')
    L.append("MIT. Les marques, logos et noms d'applications restent la propriété de leurs détenteurs.")
    L.append('')

    # ── Footer auto-sync ─────────────────────────────────────────────────
    L.append('---')
    L.append('')
    L.append('<sub>README généré automatiquement depuis la base <a href="#">africans_bc</a> — voir <a href="./scripts/generate_readme.py"><code>scripts/generate_readme.py</code></a>.</sub>')
    L.append('')

    return '\n'.join(L)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", help="Path to a local resources.json (dev)")
    p.add_argument("--stdout", action="store_true", help="Print to stdout instead of writing README.md")
    args = p.parse_args()

    if args.json:
        rows = load_local(args.json)
    elif os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_ANON_KEY"):
        rows = fetch_from_supabase()
    else:
        print("error: pass --json PATH or set SUPABASE_URL + SUPABASE_ANON_KEY", file=sys.stderr)
        return 2

    md = render(normalize(rows))

    if args.stdout:
        sys.stdout.write(md)
    else:
        README_PATH.write_text(md)
        print(f"wrote {README_PATH} ({len(md)} chars, {md.count(chr(10))} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
