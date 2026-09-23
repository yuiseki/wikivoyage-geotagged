# wikivoyage-geotagged

Every English Wikivoyage article that carries coordinates, with its text.

Published as
[`yuiseki/wikivoyage-geotagged`](https://huggingface.co/datasets/yuiseki/wikivoyage-geotagged):
29,505 articles, 240 million characters. Its card is `data/README.md`.

This is the sibling of
[wikipedia-geotagged](https://github.com/yuiseki/wikipedia-geotagged) and runs
the same code against a different wiki. 85.4% of Wikivoyage's 34,543 articles
carry a coordinate, where English Wikipedia's share is a fifth, and its
articles are three times longer.

## What is here

    src/geo_pages.py     joins geo_tags to page titles
    src/link_qids.py     attaches a Wikidata id to each article
    src/extract_text.py  pulls those articles' text out of the XML dump
    src/wikitext.py      flattens wikitext to prose
    src/publish.py       writes the Parquet and pushes it to the Hub

Three steps, from the `20260901` dumps:

    python3 src/geo_pages.py    --geo-tags voyage-geo_tags.sql.gz --page voyage-page.sql.gz --out geo_pages.jsonl
    python3 src/link_qids.py    --geo-pages geo_pages.jsonl --page-props voyage-page_props.sql.gz --out geo_pages_qid.jsonl
    python3 src/extract_text.py --dump voyage-pages-articles.xml.bz2 --geo-pages geo_pages_qid.jsonl --out corpus.jsonl.gz

`extract_text.py` takes `--base-url`, which is the only thing in the pipeline
that knows which wiki it is reading.

## What Wikivoyage puts in geo_tags

Almost nothing beyond the coordinates. On all 29,505 articles the type,
country, region and name are empty, the globe is `earth`, and there is exactly
one tag, marked primary. Wikipedia's `{{coord}}` often passes `type:city` or
`region:US-AL`; Wikivoyage's `{{geo}}` passes a latitude, a longitude and a
zoom level.

The columns are published anyway, empty, so that the two datasets have the
same shape and can be read together.

## What the dumps escape

mysqldump writes a quote inside a value as `\'`, so the bytes between the
quotes are not the value. Wikivoyage's first geotagged page is
`'s-Hertogenbosch` and came out as `\'s-Hertogenbosch`; 216 of its 29,505
titles carry an escape. `geo_pages.unescape` undoes it, and the same fix went
back into wikipedia-geotagged, where it had corrupted 2,217 `gt_name` values
without touching the titles.

## Licence

Code is Apache-2.0. The text is CC BY-SA 4.0 from Wikivoyage, confirmed
against the wiki's own `rightsinfo` rather than assumed from Wikipedia's. The
dumps are not redistributed here; everything is reproducible from them.
