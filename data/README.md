---
license: cc-by-sa-4.0
language:
- en
size_categories:
- 10K<n<100K
task_categories:
- text-generation
- fill-mask
tags:
- wikivoyage
- geography
- geotagged
- coordinates
- travel
- gazetteer
pretty_name: Geotagged Wikivoyage
configs:
- config_name: default
  data_files: articles.parquet
---

# Geotagged Wikivoyage

Every English Wikivoyage article that carries coordinates, with its text.

29,505 articles, 240,008,558 characters. Built from the `20260901` dumps.

The columns are the same as
[`yuiseki/wikipedia-geotagged`](https://huggingface.co/datasets/yuiseki/wikipedia-geotagged),
which in turn starts with
[`wikimedia/wikipedia`](https://huggingface.co/datasets/wikimedia/wikipedia)'s
`id`, `url`, `title` and `text`. The three concatenate.

Code: https://github.com/yuiseki/wikivoyage-geotagged

## Why a travel guide is worth having next to an encyclopedia

Wikivoyage is small and almost entirely about places. 29,505 of its 34,543
articles carry a coordinate, 85.4%, where English Wikipedia's share is a fifth.

It is also written differently. An encyclopedia article states what a place is;
a travel guide tells you how to get there, what the neighbouring town is called,
and which street the market is on. Its articles average 8,134 characters against
Wikipedia's 2,797, and much of that length is the names of smaller things.

| | wikivoyage-geotagged | wikipedia-geotagged |
|---|---|---|
| articles | 29,505 | 1,374,056 |
| characters | 240 M | 3.84 B |
| mean article | 8,134 | 2,797 |
| share of the wiki that is geotagged | 85.4% | 20.4% |
| with a Wikidata id | 99.6% | 99.9% |
| also in `wikidata-gazetteer` | 96.7% | 93.8% |

## Columns

| Column | |
|---|---|
| `id` | page id, as a string, like upstream |
| `url` | the article's URL |
| `title` | |
| `text` | the article, wikitext flattened to prose |
| `qid` | Wikidata item, from `page_props` |
| `lat`, `lon` | from the tag |
| `gt_dim` | roughly how large the thing is, in metres |
| `gt_globe` | `earth`, on every article here |
| `gt_primary` | true on every article here |
| `gt_type`, `gt_country`, `gt_region`, `gt_name` | always null, see below |
| `tags` | every tag on the page; exactly one on every article here |

### The four columns that are always null, and why they are here anyway

Wikivoyage fills in almost none of what `geo_tags` can hold. Of 29,505
articles, not one carries a type, a country code, a region code or a tag name,
every one is on Earth, and every one has exactly one tag marked primary.
Wikipedia's `{{coord}}` calls often pass `type:city` or `region:US-AL`;
Wikivoyage's `{{geo}}` passes a latitude, a longitude and a zoom level, and
that is all.

The columns are kept so that this dataset and `wikipedia-geotagged` have the
same shape and can be read together, for the same reason `url` is kept when it
could be computed from the title. That they are empty is a fact about
Wikivoyage, and the way to filter here is to join `qid` against
[`wikidata-gazetteer`](https://huggingface.co/datasets/yuiseki/wikidata-gazetteer)
and use its `instance_of`.

## What is here that is not a place

3.3% of the articles have no Wikidata item in `wikidata-gazetteer`. Wikivoyage
attaches coordinates to itineraries, travel topics and phrasebooks as well as
to destinations, and a few of its destinations have no Wikidata item at all.

This takes everything `geo_tags` lists, mechanically, and leaves the filtering
to you.

## How dense in place names is it

Measured against the English names in `wikidata-gazetteer`, languages excluded,
a one-word name needing 100 sitelinks, on a sample of 20,000 articles:

| | wikivoyage-geotagged | wikipedia-geotagged |
|---|---|---|
| mentions per 1,000 characters | 3.85 | 5.46 |
| articles naming at least one place | 99.2% | 99.7% |
| distinct names, per 20,000 articles | 48,103 | 34,642 |
| one-word matches at a sentence start | 2.8% | 1.8% |

Less dense, more varied. Wikipedia packs more place names into the same number
of characters; a Wikivoyage article, being three times longer, names more
distinct places than a Wikipedia one does. Which matters depends on whether you
are counting characters or documents.

The last row is the measurement's own error bar: a single capitalised word at
the start of a sentence is where false positives gather. Wikivoyage's imperative
register (`Take the bus`, `Connect through`) puts more matches there than
Wikipedia's does, though both are far below the 15.2% of UN documents.

## What is not here

Only English. `geo_tags` exists for every language edition and the same code
would build them.

Redirects are dropped, and so are pages outside the article namespace.

The text is the current revision as of the dump, with wikitext flattened:
templates and tables are unwrapped rather than removed, because a Wikivoyage
listing (`{{see|name=...|address=...}}`) holds the names the article is worth
reading for.
