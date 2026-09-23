#!/usr/bin/env python3
"""Which English Wikipedia articles are about a place, and what are they called?

Two dumps answer this together. `geo_tags` is the GeoData extension's table of
coordinates attached to pages, so a page id appearing there is a page about
something with a location. `page` maps a page id to its title and namespace.

Neither is a corpus. The point of joining them first is to see what 1.4 million
geographic articles actually are before downloading the 25.7 GB of article text
that would be needed to read them.

The SQL dumps put their values on the lines after `INSERT INTO ... VALUES`, not
on the same line, which is why these are parsed by scanning for tuples rather
than by splitting on the INSERT.
"""
import argparse
import collections
import gzip
import json
import re

# The whole row, not the first eight columns. gt_globe carries moon, mars,
# venus, mercury and titan as well as earth; gt_country and gt_region hold ISO
# codes on 41.3% and 14.2% of tags; gt_name is set on 833,597. None of it can
# be recomputed from what is kept, so all of it is kept.
#
# (gt_id, gt_page_id, gt_globe, gt_primary, gt_lat, gt_lon, gt_dim, gt_type,
#  gt_name, gt_country, gt_region, gt_lat_int, gt_lon_int)
GEO = re.compile(rb"\((\d+),(\d+),'([^']*)',(\d+),([-\d.]+|NULL),([-\d.]+|NULL),"
                 rb"([-\d]+|NULL),(NULL|'[^']*'),(NULL|'(?:[^'\\]|\\.)*'),"
                 rb"(NULL|'[^']*'),(NULL|'[^']*')")
# (page_id, page_namespace, page_title, page_is_redirect, page_is_new, ...)
PAGE = re.compile(rb"\((\d+),(\d+),'((?:[^'\\]|\\.)*)',(\d+),(\d+),")

ARTICLE_NAMESPACE = 0


def values(path):
    """Every tuple line in a MediaWiki SQL dump."""
    with gzip.open(path, "rb") as f:
        for line in f:
            if line.startswith(b"(") or b"),(" in line:
                yield line


ESCAPES = {b"0": b"\x00", b"n": b"\n", b"r": b"\r", b"Z": b"\x1a"}


def unescape(raw):
    """Undo the dump's backslash escapes.

    mysqldump writes a quote inside a value as \\', so the bytes between the
    quotes are not the value. 's-Hertogenbosch, the first geotagged page on
    Wikivoyage, came out as \\'s-Hertogenbosch until this existed.
    """
    if b"\\" not in raw:
        return raw
    out = bytearray()
    i = 0
    while i < len(raw):
        if raw[i:i + 1] == b"\\" and i + 1 < len(raw):
            c = raw[i + 1:i + 2]
            out += ESCAPES.get(c, c)
            i += 2
        else:
            out += raw[i:i + 1]
            i += 1
    return bytes(out)


def unquote(raw):
    """A dump value: a bare NULL, or a quoted string.

    One quote comes off each end, not every quote at each end. A value ending
    in an escaped quote ends in backslash, quote, quote, and strip() cannot
    tell the delimiter from the escaped character: it took both and left the
    backslash behind.
    """
    if raw == b"NULL":
        return None
    if len(raw) >= 2 and raw[:1] == b"'" and raw[-1:] == b"'":
        raw = raw[1:-1]
    return unescape(raw).decode("utf-8", "ignore") or None


def read_geo(path):
    """page id -> every tag on it, with the primary one first.

    A page can carry several tags. The primary one is the page's own location;
    the rest are places it mentions. 44,477 pages have two and 7,173 have
    three, so dropping the others would lose a relation that nothing else
    records.
    """
    out = collections.defaultdict(list)
    for line in values(path):
        for m in GEO.finditer(line):
            pid = int(m.group(2))
            out[pid].append({
                "primary": m.group(4) == b"1",
                "lat": None if m.group(5) == b"NULL" else float(m.group(5)),
                "lon": None if m.group(6) == b"NULL" else float(m.group(6)),
                "dim": None if m.group(7) == b"NULL" else int(m.group(7)),
                "type": unquote(m.group(8)),
                "name": unquote(m.group(9)),
                "country": unquote(m.group(10)),
                "region": unquote(m.group(11)),
                "globe": m.group(3).decode("utf-8", "ignore"),
            })
    for tags in out.values():
        tags.sort(key=lambda t: not t["primary"])
    return out


def read_titles(path, wanted):
    """page id -> title, for article-namespace pages that are not redirects."""
    out = {}
    for line in values(path):
        for m in PAGE.finditer(line):
            pid = int(m.group(1))
            if pid not in wanted:
                continue
            if int(m.group(2)) != ARTICLE_NAMESPACE or m.group(4) == b"1":
                continue
            out[pid] = unescape(m.group(3)).decode("utf-8", "ignore").replace("_", " ")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--geo-tags", required=True)
    ap.add_argument("--page", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    geo = read_geo(a.geo_tags)
    print(f"geo_tags pages\t{len(geo):,}", flush=True)
    titles = read_titles(a.page, geo)
    print(f"articles, not redirects\t{len(titles):,}", flush=True)

    kinds = collections.Counter()
    with open(a.out, "w", encoding="utf-8") as f:
        for pid, title in sorted(titles.items()):
            tags = geo[pid]
            head = tags[0]
            kinds[head["type"] or "(none)"] += 1
            f.write(json.dumps({
                "page_id": pid,
                "title": title,
                "lat": head["lat"], "lon": head["lon"],
                "gt_type": head["type"], "gt_globe": head["globe"],
                "gt_dim": head["dim"], "gt_country": head["country"],
                "gt_region": head["region"], "gt_name": head["name"],
                "gt_primary": head["primary"],
                "tags": tags,
            }, ensure_ascii=False) + "\n")
    print("gt_type\tcount")
    for k, n in kinds.most_common(15):
        print(f"{k}\t{n:,}")


if __name__ == "__main__":
    main()
