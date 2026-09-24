#!/usr/bin/env python3
"""Push the corpus and the files that explain it to the Hub.

Laid out the way wikimedia/wikipedia lays itself out: one subset per dump and
language, named {dump}.{lang}, holding train-NNNNN-of-NNNNN.parquet. Code
written to read that dataset reads this one by changing the repository name,
and a second language or a later dump is added rather than swapped in.

Streamed into Parquet rather than held as a datasets.Dataset: 234 million
characters across 29,505 articles costs several times its own size as Python
objects, and Parquet is the published form anyway. The same code as
wikipedia-geotagged, which needs the streaming far more.

Data first, card last. Nothing here rewrites the card, so this ordering means
the repository is never in a state where the card describes files that have not
arrived.

    python3 src/publish.py --jsonl corpus.jsonl.gz --dump 20260901 --lang en
    python3 src/publish.py --jsonl corpus.jsonl.gz --dump 20260901 --lang en --push
"""
import argparse
import json
import os
import sys

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
REPO = "yuiseki/wikivoyage-geotagged"
BATCH = 5000
# Upstream's English subset is 41 shards of about 500 MB. Splitting keeps any
# one download small and lets the viewer read the first shard without the rest.
SHARD_BYTES = 400_000_000


def shard_name(index, total):
    """train-00003-of-00041.parquet, which is what the Hub globs for."""
    return f"train-{index:05d}-of-{total:05d}.parquet"


def subset_glob(subset):
    """What the card's data_files path has to say for this subset."""
    return f"{subset}/train-*"


def stale_shards(subset, published, uploading):
    """Files in this subset that the upload does not replace.

    The Hub globs {subset}/train-*, so a subset that grows from four shards to
    five leaves train-00000-of-00004 sitting beside train-00000-of-00005 and
    every row is read twice. The count is part of the name, so a rebuild that
    changes it replaces nothing.
    """
    keep = set(uploading)
    prefix = subset + "/"
    return [p for p in published
            if p.startswith(prefix) and p[len(prefix):] not in keep]


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


def to_parquet(jsonl, out_dir):
    """Write the corpus as shards under out_dir, and report what went in.

    The shard count is in every shard's name, so the files are written under
    temporary names and renamed once the count is known. Row groups are
    flushed as they go, so the file on disk is how the size is judged.
    """
    import gzip
    import pyarrow as pa
    import pyarrow.parquet as pq

    sch = schema()
    fields = sch.names
    os.makedirs(out_dir, exist_ok=True)
    for stale in os.listdir(out_dir):
        os.remove(os.path.join(out_dir, stale))

    parts = []
    writer = None
    path = None

    def open_shard():
        nonlocal writer, path
        path = os.path.join(out_dir, f"part-{len(parts):05d}.parquet")
        writer = pq.ParquetWriter(path, sch, compression="zstd")

    def close_shard():
        nonlocal writer
        writer.close()
        writer = None
        parts.append(path)

    batch = {k: [] for k in fields}
    n = chars = 0
    opener = gzip.open if jsonl.endswith(".gz") else open
    open_shard()
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
                    if os.path.getsize(path) >= SHARD_BYTES:
                        close_shard()
                        open_shard()
        if batch["id"]:
            writer.write_table(pa.Table.from_pydict(batch, schema=sch))
    finally:
        if writer is not None:
            close_shard()

    total = len(parts)
    names = []
    for i, part in enumerate(parts):
        final = os.path.join(out_dir, shard_name(i, total))
        os.rename(part, final)
        names.append(final)
    return n, chars, names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", required=True)
    ap.add_argument("--dump", required=True,
                    help="the dump date, like 20260901; half of the subset name")
    ap.add_argument("--lang", required=True,
                    help="the wiki's language code; the other half")
    ap.add_argument("--out-dir", default=None,
                    help="where to write the shards; default data/<subset>")
    ap.add_argument("--card", default=os.path.join(BASE, "data/README.md"))
    ap.add_argument("--extra", nargs="*", default=[
        os.path.join(BASE, "data/LICENSE"),
        os.path.join(BASE, "data/provenance.yaml")])
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--push", action="store_true")
    a = ap.parse_args()

    subset = f"{a.dump}.{a.lang}"
    out_dir = a.out_dir or os.path.join(BASE, "data", subset)
    n, chars, shards = to_parquet(a.jsonl, out_dir)
    size = sum(os.path.getsize(p) for p in shards)
    print(f"{subset}: {n:,} articles, {chars:,} characters")
    print(f"  {len(shards)} shards, {size/1e9:.2f} GB")

    card = open(a.card, encoding="utf-8").read()
    if f"{n:,}" not in card:
        raise SystemExit(f"the card does not mention {n:,} articles; rebuild it")
    # The card is what the Hub reads to find the files. A subset whose config
    # is missing uploads cleanly and is invisible.
    if f"- config_name: {subset}" not in card:
        raise SystemExit(f"the card declares no config for {subset}")
    if subset_glob(subset) not in card:
        raise SystemExit(f"the card does not point at {subset_glob(subset)}")
    print(f"card declares {subset}")
    for p in [a.card] + a.extra:
        if not os.path.exists(p):
            raise SystemExit(f"missing {p}")

    if not a.push:
        print("dry run. pass --push to upload")
        return 0

    from huggingface_hub import HfApi, CommitOperationDelete
    api = HfApi()
    api.create_repo(a.repo, repo_type="dataset", exist_ok=True)

    # Before anything lands, work out what this upload will orphan. Deleting
    # after the new shards are up keeps the subset readable throughout: a
    # moment of duplicated rows is recoverable, a moment of missing ones is
    # what a reader downloads.
    published = api.list_repo_files(a.repo, repo_type="dataset")
    orphans = stale_shards(subset, published, [os.path.basename(p) for p in shards])

    for i, path in enumerate(shards, 1):
        name = os.path.basename(path)
        print(f"uploading {subset}/{name}  ({i}/{len(shards)}) ...", flush=True)
        api.upload_file(path_or_fileobj=path, path_in_repo=f"{subset}/{name}",
                        repo_id=a.repo, repo_type="dataset")
    for p in a.extra:
        api.upload_file(path_or_fileobj=p, path_in_repo=os.path.basename(p),
                        repo_id=a.repo, repo_type="dataset")
    api.upload_file(path_or_fileobj=a.card, path_in_repo="README.md",
                    repo_id=a.repo, repo_type="dataset")
    if orphans:
        print(f"removing {len(orphans)} shard(s) the rebuild replaced:")
        for p in orphans:
            print(f"  {p}")
        api.create_commit(
            repo_id=a.repo, repo_type="dataset",
            operations=[CommitOperationDelete(path_in_repo=p) for p in orphans],
            commit_message=f"Remove the shards {subset} no longer uses")
    print(f"pushed to https://huggingface.co/datasets/{a.repo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
