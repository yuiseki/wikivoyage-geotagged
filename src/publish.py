#!/usr/bin/env python3
"""Push the corpus and the files that explain it to the Hub.

Streamed into Parquet rather than held as a datasets.Dataset: 3.8 billion
characters across 1.37 million articles costs several times its own size as
Python objects, and Parquet is the published form anyway.

Data first, card last. Nothing here rewrites the card, so this ordering means
the repository is never in a state where the card describes files that have not
arrived.

    python3 src/publish.py             # dry run, checks the card against the data
    python3 src/publish.py --push      # uploads
"""
import argparse
import json
import os
import sys

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
REPO = "yuiseki/wikivoyage-geotagged"
# What the file is called in the repository, which is what the card's
# data_files names. The local file can be called anything.
PATH_IN_REPO = "articles.parquet"
BATCH = 5000


def schema():
    import pyarrow as pa
    tag = pa.struct([("primary", pa.bool_()), ("lat", pa.float64()),
                     ("lon", pa.float64()), ("dim", pa.int64()),
                     ("type", pa.string()), ("name", pa.string()),
                     ("country", pa.string()), ("region", pa.string()),
                     ("globe", pa.string())])
    # The first four are wikimedia/wikipedia's, in its order and under its
    # names, so that code written for that dataset works here unchanged.
    return pa.schema([
        ("id", pa.string()), ("url", pa.string()), ("title", pa.string()),
        ("text", pa.string()), ("qid", pa.string()),
        ("lat", pa.float64()), ("lon", pa.float64()),
        ("gt_type", pa.string()), ("gt_globe", pa.string()),
        ("gt_dim", pa.int64()), ("gt_country", pa.string()),
        ("gt_region", pa.string()), ("gt_name", pa.string()),
        ("gt_primary", pa.bool_()), ("tags", pa.list_(tag)),
    ])


def to_parquet(jsonl, out):
    import gzip
    import pyarrow as pa
    import pyarrow.parquet as pq

    sch = schema()
    fields = sch.names
    writer = pq.ParquetWriter(out, sch, compression="zstd")
    batch = {k: [] for k in fields}
    n = chars = 0
    opener = gzip.open if jsonl.endswith(".gz") else open
    try:
        with opener(jsonl, "rt", encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                for k in fields:
                    batch[k].append(r.get(k))
                n += 1
                chars += len(r.get("text") or "")
                if len(batch["id"]) >= BATCH:
                    writer.write_table(pa.Table.from_pydict(batch, schema=sch))
                    batch = {k: [] for k in fields}
        if batch["id"]:
            writer.write_table(pa.Table.from_pydict(batch, schema=sch))
    finally:
        writer.close()
    return n, chars


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", required=True)
    ap.add_argument("--parquet", default=None)
    ap.add_argument("--card", default=os.path.join(BASE, "data/README.md"))
    ap.add_argument("--extra", nargs="*", default=[
        os.path.join(BASE, "data/LICENSE"),
        os.path.join(BASE, "data/provenance.yaml")])
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--push", action="store_true")
    a = ap.parse_args()

    parquet = a.parquet or os.path.join(BASE, "data/articles.parquet")
    n, chars = to_parquet(a.jsonl, parquet)
    print(f"{n:,} articles, {chars:,} characters")
    print(f"  {os.path.basename(parquet)} {os.path.getsize(parquet)/1e9:.2f} GB")

    card = open(a.card, encoding="utf-8").read()
    if f"{n:,}" not in card:
        raise SystemExit(f"the card does not mention {n:,} articles; rebuild it")
    print("card mentions the article count")
    for p in [a.card] + a.extra:
        if not os.path.exists(p):
            raise SystemExit(f"missing {p}")

    if not a.push:
        print("dry run. pass --push to upload")
        return 0

    from huggingface_hub import HfApi
    api = HfApi()
    api.create_repo(a.repo, repo_type="dataset", exist_ok=True)
    print(f"uploading {PATH_IN_REPO} ...", flush=True)
    api.upload_file(path_or_fileobj=parquet, path_in_repo=PATH_IN_REPO,
                    repo_id=a.repo, repo_type="dataset")
    for p in a.extra:
        api.upload_file(path_or_fileobj=p, path_in_repo=os.path.basename(p),
                        repo_id=a.repo, repo_type="dataset")
    api.upload_file(path_or_fileobj=a.card, path_in_repo="README.md",
                    repo_id=a.repo, repo_type="dataset")
    print(f"pushed to https://huggingface.co/datasets/{a.repo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
