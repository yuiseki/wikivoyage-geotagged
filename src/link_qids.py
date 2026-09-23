#!/usr/bin/env python3
"""Attach a Wikidata id to each geographic article.

`page_props` carries `wikibase_item` for every article that has a Wikidata
item, which turns a title into a Q-number and so into everything the gazetteer
knows: what class the thing is, what contains it, how many Wikipedias write
about it.

Matching titles as strings got 52.8% and could not tell Alexander the Great
from a town. This is the same join done properly.
"""
import argparse
import collections
import gzip
import json
import re

PROP = re.compile(rb"\((\d+),'([^']*)','((?:[^'\\]|\\.)*)'")


def read_qids(path, wanted):
    out = {}
    with gzip.open(path, "rb") as f:
        for line in f:
            if not line.startswith(b"(") and b"),(" not in line:
                continue
            for m in PROP.finditer(line):
                if m.group(2) != b"wikibase_item":
                    continue
                pid = int(m.group(1))
                if pid in wanted:
                    out[pid] = m.group(3).decode("utf-8", "ignore")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--geo-pages", required=True)
    ap.add_argument("--page-props", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    pages = {}
    with open(a.geo_pages, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            pages[r["page_id"]] = r
    print(f"geographic articles\t{len(pages):,}", flush=True)

    qids = read_qids(a.page_props, set(pages))
    print(f"with a wikidata item\t{len(qids):,} "
          f"({len(qids)/len(pages)*100:.1f}%)", flush=True)

    with open(a.out, "w", encoding="utf-8") as out:
        for pid, r in sorted(pages.items()):
            r["qid"] = qids.get(pid)
            out.write(json.dumps(r, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
