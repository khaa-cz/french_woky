#!/usr/bin/env python3
import json
import os
import re
from pathlib import Path
from collections import defaultdict


def natural_key(name: str):
    m = re.search(r"(\d+)", name)
    return (int(m.group(1)) if m else float('inf'), name)


def load_items(words_dir: Path):
    files = sorted([p for p in words_dir.glob('*.json')], key=lambda p: natural_key(p.name))
    items = []
    for fpath in files:
        try:
            with fpath.open('r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, list):
                continue
            for idx, it in enumerate(data, start=1):
                fr = (it.get('fr') or '').strip()
                de = (it.get('de') or '').strip()
                pron = (it.get('pron') or '').strip()
                if fr and de:
                    items.append({
                        'fr': fr,
                        'de': de,
                        'pron': pron,
                        'file': fpath.name,
                        'index': idx,
                    })
        except Exception as e:
            print(f"WARN: failed to parse {fpath.name}: {e}")
    return items


def report_duplicates(items):
    by_pair = defaultdict(list)
    by_fr = defaultdict(list)
    by_de = defaultdict(list)

    for it in items:
        key_pair = (it['fr'], it['de'])
        by_pair[key_pair].append((it['file'], it['index']))
        by_fr[it['fr']].append((it['de'], it['file'], it['index']))
        by_de[it['de']].append((it['fr'], it['file'], it['index']))

    print('=== Duplicate (fr, de) pairs ===')
    pair_dups = 0
    for (fr, de), locs in sorted(by_pair.items()):
        if len(locs) > 1:
            pair_dups += 1
            locs_s = ', '.join([f"{f}#{i}" for f, i in locs])
            print(f"- {fr} ⇄ {de}  -> {locs_s}")
    if pair_dups == 0:
        print('None')

    print('\n=== Duplicate FR with multiple entries ===')
    fr_dups = 0
    for fr, entries in sorted(by_fr.items()):
        if len(entries) > 1:
            fr_dups += 1
            variants = '; '.join([f"{de} ({f}#{i})" for de, f, i in entries])
            unique_des = sorted(set([de for de, _, _ in entries]))
            print(f"- {fr}  -> {variants} | distinct DE: {len(unique_des)}")
    if fr_dups == 0:
        print('None')

    print('\n=== Duplicate DE with multiple entries ===')
    de_dups = 0
    for de, entries in sorted(by_de.items()):
        if len(entries) > 1:
            de_dups += 1
            variants = '; '.join([f"{fr} ({f}#{i})" for fr, f, i in entries])
            unique_frs = sorted(set([fr for fr, _, _ in entries]))
            print(f"- {de}  -> {variants} | distinct FR: {len(unique_frs)}")
    if de_dups == 0:
        print('None')

    total = len(items)
    print(f"\nScanned {total} items across {len(set([it['file'] for it in items]))} files.")


def main():
    base = Path(__file__).resolve().parent.parent
    words_dir = base / 'words'
    if not words_dir.is_dir():
        print(f"ERROR: words directory not found at {words_dir}")
        return 1
    items = load_items(words_dir)
    report_duplicates(items)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
