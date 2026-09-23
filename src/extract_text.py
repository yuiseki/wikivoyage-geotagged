#!/usr/bin/env python3
"""Pull the text of the geographic articles out of the article dump.

The dump is 25.7 GB compressed and about 100 GB expanded, so nothing is held:
lbzip2 streams it in, iterparse walks it an element at a time, each page is
cleared as soon as it is read, and the output is written gzipped as it goes.
The only thing kept in memory is which page ids are wanted, about 165 MB.

Only articles named in geo_pages_qid.jsonl are kept, so the Wikidata id and the
coordinates travel with the text.
"""
import argparse
import gzip
import json
import subprocess
import sys
from urllib.parse import quote
import xml.etree.ElementTree as ET

from wikitext import clean  # noqa: E402


def pages(stream):
    for _, elem in ET.iterparse(stream, events=("end",)):
        if elem.tag.rsplit("}", 1)[-1] != "page":
            continue
        pid = elem.findtext("./{*}id")
        yield (int(pid) if pid and pid.isdigit() else None,
               elem.findtext("./{*}title") or "",
               elem.findtext("./{*}revision/{*}text") or "")
        elem.clear()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--geo-pages", required=True)
    ap.add_argument("--out", required=True, help="written gzipped")
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--base-url", default="https://en.wikivoyage.org/wiki/",
                    help="prefix for the url column; the only site-specific "
                         "thing in this file")
    a = ap.parse_args()

    wanted = {}
    with open(a.geo_pages, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            wanted[r["page_id"]] = r
    print(f"wanted\t{len(wanted):,}", flush=True)

    proc = subprocess.Popen(["lbzip2", "-dc", "-n", str(a.threads), a.dump],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    kept = seen = empty = 0
    chars = 0
    try:
        with gzip.open(a.out, "wt", encoding="utf-8", compresslevel=6) as out:
            for pid, title, text in pages(proc.stdout):
                seen += 1
                r = wanted.get(pid)
                if r is None:
                    continue
                body = clean(text).strip()
                if not body:
                    empty += 1
                    continue
                chars += len(body)
                # The first four columns are wikimedia/wikipedia's, in its
                # order and under its names, so that anything written against
                # that dataset works against this one. url is derivable from
                # the title, and kept anyway for the same reason.
                #
                # Nothing else here restates what can be computed. No lang,
                # source or licence, which are properties of the dataset; no
                # character count, which is len(text); no instance_of, which
                # is a join away on qid.
                out.write(json.dumps({
                    "id": str(pid),
                    "url": a.base_url
                           + quote(title.replace(" ", "_"), safe="/:()',!*-"),
                    "title": title,
                    "text": body,
                    "qid": r.get("qid"),
                    "lat": r.get("lat"), "lon": r.get("lon"),
                    "gt_type": r.get("gt_type"), "gt_globe": r.get("gt_globe"),
                    "gt_dim": r.get("gt_dim"), "gt_country": r.get("gt_country"),
                    "gt_region": r.get("gt_region"), "gt_name": r.get("gt_name"),
                    "gt_primary": r.get("gt_primary"),
                    "tags": r.get("tags"),
                }, ensure_ascii=False) + "\n")
                kept += 1
                if kept % 100_000 == 0:
                    print(f"  {kept:,} kept of {seen:,} seen, "
                          f"{chars/1e9:.2f} G characters", flush=True)
    finally:
        proc.stdout.close()
        proc.wait()
    print(f"pages seen\t{seen:,}")
    print(f"geographic articles written\t{kept:,}")
    print(f"empty after cleaning\t{empty:,}")
    print(f"characters\t{chars:,}")


if __name__ == "__main__":
    sys.exit(main())
