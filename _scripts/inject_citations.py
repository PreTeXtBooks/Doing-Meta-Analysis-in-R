#!/usr/bin/env python3
"""
inject_citations.py

Runs the fixed rmd_to_ptx_converter on each chapter and merges citations
(xref tags) from the fresh conversion into the existing PTX files.

Strategy:
  1. Run the converter to get a freshly-converted PTX (with xref citations).
  2. Match paragraphs between fresh PTX and existing PTX by plain-text similarity.
  3. For each matched pair where fresh PTX has xref tags, update the existing
     paragraph with the fresh version.
  4. Preserve any paragraphs unique to the existing PTX (manually added).

Usage:
  python3 _scripts/inject_citations.py
"""

import re
import sys
import os
import difflib
import subprocess
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONVERTER = os.path.join(REPO, '_scripts', 'rmd_to_ptx_converter.py')

FILE_MAP = [
    ('03-introduction.Rmd',               'pretext/source/ch_introduction.ptx'),
    ('04-discovering_R.Rmd',              'pretext/source/ch_discovering_r.ptx'),
    ('05-effect_sizes.Rmd',               'pretext/source/ch_effect_sizes.ptx'),
    ('06-pooling_effect_sizes.Rmd',       'pretext/source/ch_pooling_effect_sizes.ptx'),
    ('07-heterogeneity.Rmd',              'pretext/source/ch_heterogeneity.ptx'),
    ('08-forestplots.Rmd',                'pretext/source/ch_forest_plots.ptx'),
    ('09-subgroup.Rmd',                   'pretext/source/ch_subgroup_analyses.ptx'),
    ('10-metareg.Rmd',                    'pretext/source/ch_meta_regression.ptx'),
    ('11-publication-bias.Rmd',           'pretext/source/ch_publication_bias.ptx'),
    ('12-mlma.Rmd',                       'pretext/source/ch_multilevel_meta_analysis.ptx'),
    ('13-sem.Rmd',                        'pretext/source/ch_sem_meta_analysis.ptx'),
    ('14-netwma.Rmd',                     'pretext/source/ch_network_meta_analysis.ptx'),
    ('15-bayesianma.Rmd',                 'pretext/source/ch_bayesian_meta_analysis.ptx'),
    ('16-power-analysis.Rmd',             'pretext/source/ch_power_analysis.ptx'),
    ('17-risk-of-bias-plots.Rmd',         'pretext/source/ch_risk_of_bias_plots.ptx'),
    ('18-reporting-reproducibility.Rmd',  'pretext/source/ch_reporting_reproducibility.ptx'),
    ('19-effect-size-calculation.Rmd',    'pretext/source/ch_effect_size_calculation_conversion.ptx'),
    ('01-preface.Rmd',                    'pretext/source/fm_preface.ptx'),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def strip_xml_for_match(text):
    """Remove XML tags (including xref) and normalize whitespace for comparison."""
    # Remove xref citation tags
    text = re.sub(r'<xref[^>]*/>', '', text)
    # Remove prose citation patterns like "(Author, Year; see )"
    text = re.sub(r'\([^)]*see\s+\)', '', text)
    # Remove all other XML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def get_paragraphs(content):
    """
    Extract <p>...</p> blocks as a list of dicts with 'raw' content and 'plain' text.
    Handles both single-line and multi-line paragraphs.
    """
    paras = []
    # Use regex to find all <p>...</p> blocks (non-greedy, dotall)
    for m in re.finditer(r'(<p>.*?</p>)', content, re.DOTALL):
        raw = m.group(1)
        plain = strip_xml_for_match(raw)
        paras.append({'raw': raw, 'plain': plain, 'start': m.start(), 'end': m.end()})
    return paras


def similarity(a, b):
    """Return text similarity ratio between two strings."""
    return difflib.SequenceMatcher(None, a, b).ratio()


def find_best_match(para_plain, candidates, min_score=0.55):
    """Find the candidate paragraph most similar to para_plain."""
    best_score = 0
    best_idx = -1
    # For efficiency, only compare if plain texts share significant words
    para_words = set(para_plain.lower().split())
    for i, cand in enumerate(candidates):
        if not cand['plain']:
            continue
        cand_words = set(cand['plain'].lower().split())
        # Quick pre-filter: must share at least 30% of words
        if not para_words or not cand_words:
            continue
        overlap = len(para_words & cand_words) / min(len(para_words), len(cand_words))
        if overlap < 0.3:
            continue
        score = similarity(para_plain, cand['plain'])
        if score > best_score:
            best_score = score
            best_idx = i
    if best_score >= min_score:
        return best_idx, best_score
    return -1, best_score


def has_citations(para_raw):
    """Return True if a paragraph has xref citation tags."""
    return bool(re.search(r'<xref ref="[a-zA-Z]', para_raw))


def inject_citations_into_existing(existing_content, new_content):
    """
    Merge citation xref tags from new_content into existing_content.

    For each paragraph in new_content that contains citation xref tags:
      - Find the best matching paragraph in existing_content
      - Replace the matching paragraph with the new one (which has citations)

    Paragraphs unique to existing_content (manually added) are preserved.
    """
    existing_paras = get_paragraphs(existing_content)
    new_paras = get_paragraphs(new_content)

    # Only process new paragraphs that have citation xrefs
    new_cited = [(i, p) for i, p in enumerate(new_paras) if has_citations(p['raw'])]

    # Build a map: existing_para_raw -> replacement_raw
    replacements = {}
    unmatched_citations = []

    for new_idx, new_para in new_cited:
        if not new_para['plain']:
            continue
        match_idx, score = find_best_match(new_para['plain'], existing_paras)
        if match_idx >= 0:
            old_raw = existing_paras[match_idx]['raw']
            # Only replace if the existing version doesn't already have the same xrefs
            new_xrefs = set(re.findall(r'<xref ref="([^"]+)"/>', new_para['raw']))
            old_xrefs = set(re.findall(r'<xref ref="([^"]+)"/>', old_raw))
            # Get xrefs that are citation refs (not cross-refs to sections)
            new_cite_xrefs = {k for k in new_xrefs
                              if not k.startswith('fig') and k not in old_xrefs}
            if new_cite_xrefs or (new_xrefs - old_xrefs):
                replacements[old_raw] = new_para['raw']
        else:
            unmatched_citations.append((new_idx, new_para, score))

    if unmatched_citations:
        print(f"  WARNING: {len(unmatched_citations)} cited paragraphs had no match:")
        for idx, p, score in unmatched_citations[:3]:
            print(f"    [{idx}] score={score:.2f}: {p['plain'][:60]}...")
            print(f"         xrefs: {re.findall(r'<xref ref=\"([^\"]+)\"/>', p['raw'])}")

    # Apply replacements to existing_content
    # Replace exact matches of old paragraph raw content
    updated_content = existing_content
    replaced_count = 0
    for old_raw, new_raw in replacements.items():
        if old_raw in updated_content:
            # Preserve indentation: get leading whitespace from old
            # Find old_raw position and get the surrounding context
            updated_content = updated_content.replace(old_raw, new_raw, 1)
            replaced_count += 1
        else:
            print(f"  WARNING: Could not find exact match for replacement")

    print(f"  Replaced {replaced_count} paragraphs with citations")
    return updated_content


def process_chapter(rmd_file, ptx_file):
    """Process one chapter: inject citations from converted RMD into existing PTX."""
    rmd_path = os.path.join(REPO, rmd_file)
    ptx_path = os.path.join(REPO, ptx_file)

    if not os.path.exists(rmd_path):
        print(f"  SKIP: {rmd_file} not found")
        return
    if not os.path.exists(ptx_path):
        print(f"  SKIP: {ptx_file} not found")
        return

    # Run converter to get fresh PTX with citations
    temp_ptx = os.path.join(REPO, '_temp_converted.ptx')
    try:
        result = subprocess.run(
            [sys.executable, CONVERTER, rmd_path, ptx_path, temp_ptx],
            capture_output=True, text=True, cwd=REPO
        )
        if result.returncode != 0:
            print(f"  ERROR: converter failed: {result.stderr[:200]}")
            return

        with open(temp_ptx, 'r', encoding='utf-8') as f:
            new_content = f.read()
    finally:
        if os.path.exists(temp_ptx):
            os.remove(temp_ptx)

    with open(ptx_path, 'r', encoding='utf-8') as f:
        existing_content = f.read()

    # Count citations in new content
    new_cite_count = len(re.findall(r'<xref ref="[a-zA-Z]', new_content))
    existing_cite_count = len(re.findall(r'<xref ref="[a-zA-Z]', existing_content))
    print(f"  Citations: existing={existing_cite_count}, new={new_cite_count}")

    if new_cite_count == 0:
        print(f"  No citations in converted output, skipping")
        return

    updated_content = inject_citations_into_existing(existing_content, new_content)

    final_cite_count = len(re.findall(r'<xref ref="[a-zA-Z]', updated_content))
    print(f"  Result: {final_cite_count} citations in updated file")

    with open(ptx_path, 'w', encoding='utf-8') as f:
        f.write(updated_content)

    print(f"  Written: {ptx_file}")


def main():
    os.chdir(REPO)
    for rmd_file, ptx_file in FILE_MAP:
        print(f"\nProcessing: {rmd_file} → {ptx_file}")
        process_chapter(rmd_file, ptx_file)
    print("\nDone.")


if __name__ == '__main__':
    main()
