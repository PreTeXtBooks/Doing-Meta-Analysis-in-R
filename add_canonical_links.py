#!/usr/bin/env python3
"""
Insert <link rel="canonical"> tags into the built HTML pages that have a
direct counterpart on the original, published site (doing-meta.guide).

This book is a PreTeXt conversion of "Doing Meta-Analysis with R: A
Hands-on Guide". Since this HTML edition is freely readable with no
download option (no PDF/EPUB offered alongside it), pages that mirror
original content must carry a canonical link back to the original page.

Run this after `pretext build web` (see .github/workflows/deploy-pretext.yml).
"""

import sys
from pathlib import Path

ORIGINAL_SITE = "https://doing-meta.guide"

# Maps built HTML filename (relative to the web output directory) to the
# URL slug of the matching page on the original site. Verified against the
# live site's navigation and page content.
CANONICAL_SLUGS = {
    # Core chapters
    "intro.html": "intro",
    "discovering-R.html": "discovering-r",
    "effects.html": "effects",
    "pooling-es.html": "pooling-es",
    "heterogeneity.html": "heterogeneity",
    "forest.html": "forest",
    "subgroup.html": "subgroup",
    "metareg.html": "metareg",
    "pub-bias.html": "pub-bias",
    "multilevel-ma.html": "multilevel-ma",
    "sem.html": "sem",
    "netwma.html": "netwma",
    "bayesian-ma.html": "bayesian-ma",
    "power.html": "power",
    "risk-of-bias-plots.html": "risk-of-bias-plots",
    "reporting-reproducibility.html": "reporting-reproducibility",
    "es-calc.html": "es-calc",
    # Front/back matter and appendix sections with a direct original counterpart
    "preface.html": "preface",
    "about-authors.html": "about-the-authors",
    "citing-this-guide.html": "citing-this-guide-1",
    "references.html": "references",
    "qanda.html": "qanda",
    "formula.html": "formula",
    "symbollist.html": "symbollist",
    "attr.html": "attr",
    "corrections.html": "corrections",
}


def add_canonical_link(html_path: Path, canonical_url: str) -> bool:
    text = html_path.read_text(encoding="utf-8")

    if 'rel="canonical"' in text:
        return False

    title_close = "</title>"
    idx = text.find(title_close)
    if idx == -1:
        print(f"  Warning: no <title> found in {html_path.name}, skipping")
        return False

    insert_at = idx + len(title_close)
    tag = f'\n<link rel="canonical" href="{canonical_url}">'
    text = text[:insert_at] + tag + text[insert_at:]
    html_path.write_text(text, encoding="utf-8")
    return True


def main():
    script_dir = Path(__file__).parent
    web_dir = script_dir / "pretext" / "output" / "web"

    if not web_dir.is_dir():
        print(f"Error: build output directory not found: {web_dir}")
        return 1

    print(f"Adding canonical links in {web_dir}")

    updated = 0
    missing = 0
    for filename, slug in CANONICAL_SLUGS.items():
        html_path = web_dir / filename
        if not html_path.exists():
            print(f"  Warning: expected output file not found: {filename}")
            missing += 1
            continue

        canonical_url = f"{ORIGINAL_SITE}/{slug}"
        if add_canonical_link(html_path, canonical_url):
            updated += 1
            print(f"  {filename} -> {canonical_url}")

    print(f"\nComplete! Added canonical links to {updated} page(s).")
    if missing:
        print(f"Warning: {missing} expected page(s) were missing from the build output.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
