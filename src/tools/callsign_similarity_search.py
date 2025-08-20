#!/usr/bin/env python3
import argparse, json, time, traceback, os
from datetime import datetime
from pymongo import MongoClient
from pymongo import errors
from dotenv import load_dotenv

# -----------------------------------------------------------------------------
# Connection helper (integrated)
# -----------------------------------------------------------------------------
def get_database(uri_override: str | None, db_override: str | None):
    """
    Returns (db, client). If uri/db are not provided explicitly, load from env:
      DATABASE_USER, DATABASE_TOKEN, DATABASE_IP, DATABASE_NAME
    """
    load_dotenv()

    if uri_override:
        if not db_override:
            raise RuntimeError("--db is required when you pass --uri")
        client = MongoClient(uri_override)
        return client[db_override], client

    db_user = os.getenv("DATABASE_USER")
    db_token = os.getenv("DATABASE_TOKEN")
    db_ip = os.getenv("DATABASE_IP")
    db_name = os.getenv("DATABASE_NAME")
    if not all([db_user, db_token, db_ip, db_name]):
        raise RuntimeError("Database env vars missing. Need DATABASE_USER, DATABASE_TOKEN, DATABASE_IP, DATABASE_NAME")
    uri = (
        f"mongodb://{db_user}:{db_token}@{db_ip}:27017/"
        f"?directConnection=true&serverSelectionTimeoutMS=2000&authSource={db_name}"
    )
    client = MongoClient(uri)
    return client[db_name], client

# -----------------------------------------------------------------------------
# Progress helpers
# -----------------------------------------------------------------------------
def nice_ms(ms):
    if ms < 1_000: return f"{ms:.0f} ms"
    s = ms / 1_000
    if s < 60: return f"{s:.2f} s"
    m = int(s // 60); r = s % 60
    return f"{m}m {r:.1f}s"

def run_count(coll, pipeline_prefix, allow_disk):
    cnt_pipe = list(pipeline_prefix) + [{"$count": "n"}]
    t0 = time.perf_counter()
    try:
        doc = next(coll.aggregate(cnt_pipe, allowDiskUse=allow_disk), None)
        n = (doc or {}).get("n", 0)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return n, elapsed_ms, None
    except Exception as e:
        return None, None, e

def run_peek(coll, pipeline_prefix, allow_disk, peek_n):
    if peek_n <= 0: return []
    peek_pipe = list(pipeline_prefix) + [{"$limit": int(peek_n)}]
    try:
        return list(coll.aggregate(peek_pipe, allowDiskUse=allow_disk))
    except Exception:
        return []

def stream_results(coll, pipeline, allow_disk, batch_size):
    total = 0
    t0 = time.perf_counter()
    cursor = coll.aggregate(pipeline, allowDiskUse=allow_disk, batchSize=batch_size)
    try:
        for _ in cursor:
            total += 1
            if total % batch_size == 0:
                elapsed_ms = (time.perf_counter() - t0) * 1000
                print(f"[stream] returned {total} docs so far … ({nice_ms(elapsed_ms)})", flush=True)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        print(f"[stream] done. total={total} in {nice_ms(elapsed_ms)}")
    finally:
        try:
            cursor.close()
        except Exception:
            pass
    return total

# -----------------------------------------------------------------------------
# Define your aggregation here (can also load from --pipeline-file)
# This is the “USAF-tag seeds, then cross-match callsigns” pipeline we built.
# -----------------------------------------------------------------------------
def build_pipeline():
    usaf_tag_regex = r"\]\[[^\]]{3}\]\[USAF\]"  # ][XXX][USAF], case-insensitive
    return [
        # 1) Seeds: any pastCallsign matching our tag
        {
            "$match": {
                "pastCallsigns": {
                    "$elemMatch": {"$regex": usaf_tag_regex, "$options": "i"}
                }
            }
        },
        # 2) Unique, non-empty originals
        {
            "$project": {
                "accountID": 1,
                "currentCallsign": 1,
                "lastOnline": 1,
                "seedPastOriginal": {
                    "$filter": {
                        "input": {"$setUnion": ["$pastCallsigns", []]},
                        "as": "cs",
                        "cond": {
                            "$and": [
                                {"$ne": ["$$cs", None]},
                                # NOTE: fixed spacing around $trim (this was a syntax error before)
                                {"$ne": [{"$trim": {"input": "$$cs"}}, ""]}
                            ]
                        }
                    }
                }
            }
        },
        # 3) Pair (original, normalized)
        {
            "$project": {
                "accountID": 1,
                "currentCallsign": 1,
                "lastOnline": 1,
                "seedPairs": {
                    "$map": {
                        "input": "$seedPastOriginal",
                        "as": "cs",
                        "in": {
                            "original": "$$cs",
                            "norm": {"$toLower": {"$trim": {"input": "$$cs"}}}
                        }
                    }
                }
            }
        },
        {"$unwind": "$seedPairs"},
        # 4) Lookup other docs that had the same callsign (normalized)
        {
            "$lookup": {
                "from": "users",
                "let": { "seedNorm": "$seedPairs.norm", "seedACID": "$accountID" },
                "pipeline": [
                    {
                        "$addFields": {
                            "_normPast": {
                                "$map": {
                                    "input": {"$ifNull": ["$pastCallsigns", []]},
                                    "as": "p",
                                    "in": {"$toLower": {"$trim": {"input": "$$p"}}}
                                }
                            }
                        }
                    },
                    {
                        "$match": {
                            "$expr": {
                                "$and": [
                                    {"$in": ["$$seedNorm", "$_normPast"]},
                                    {"$ne": ["$accountID", "$$seedACID"]}
                                ]
                            }
                        }
                    },
                    { "$project": { "_id": 1, "accountID": 1, "currentCallsign": 1, "lastOnline": 1 } }
                ],
                "as": "matches"
            }
        },
        # 5) Keep only callsigns that produced at least one match
        {"$unwind": "$matches"},
        # 6) Group by (seed account, seed callsign)
        {
            "$group": {
                "_id": { "seedAccountID": "$accountID", "seedCallsign": "$seedPairs.original" },
                "matches": {
                    "$addToSet": {
                        "_id": "$matches._id",
                        "accountID": "$matches.accountID",
                        "currentCallsign": "$matches.currentCallsign",
                        "lastOnline": "$matches.lastOnline"
                    }
                }
            }
        },
        # 7) Group per seed account
        {
            "$group": {
                "_id": "$_id.seedAccountID",
                "callsignMatches": {
                    "$push": { "callsign": "$_id.seedCallsign", "matchedDocs": "$matches" }
                }
            }
        },
        # 8) Final tidy
        { "$project": { "_id": 0, "accountID": "$_id", "callsignMatches": 1 } },
        { "$sort": { "accountID": 1 } }
    ]

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Run Mongo aggregation with per-stage progress (env-aware).")
    ap.add_argument("--uri", help="Override MongoDB URI (otherwise uses env vars)")
    ap.add_argument("--db", help="Database name (required with --uri; optional if using env)")
    ap.add_argument("--coll", required=True, help="Collection name (e.g., users)")
    ap.add_argument("--pipeline-file", help="JSON file containing the aggregation array")
    ap.add_argument("--allow-disk-use", action="store_true", help="Pass allowDiskUse=True")
    ap.add_argument("--peek", type=int, default=0, help="Show this many docs after each stage")
    ap.add_argument("--stream-batch", type=int, default=0, help="If >0, stream final results in batches of this size")
    args = ap.parse_args()

    db, client = get_database(args.uri, args.db)
    coll = db[args.coll]

    if args.pipeline_file:
        with open(args.pipeline_file, "r", encoding="utf-8") as f:
            pipeline = json.load(f)
    else:
        pipeline = build_pipeline()

    print(f"[{datetime.now().isoformat()}] stages: {len(pipeline)}  allowDiskUse={args.allow_disk_use}")
    print("-" * 80)

    total_start = time.perf_counter()
    prefix = []
    for i, stage in enumerate(pipeline, 1):
        prefix.append(stage)
        print(f"[stage {i}/{len(pipeline)}] {json.dumps(stage, ensure_ascii=False)}")

        n, ms, err = run_count(coll, prefix, args.allow_disk_use)
        if err is None:
            print(f"  ↳ count after stage {i}: {n:,}  ({nice_ms(ms)})")
        else:
            print(f"  ↳ count failed after stage {i} (stage may not be countable).")
            print("    ", repr(err).split("\n")[0])

        if args.peek > 0:
            docs = run_peek(coll, prefix, args.allow_disk_use, args.peek)
            print(f"  ↳ peek {len(docs)} doc(s):")
            for j, d in enumerate(docs, 1):
                preview = json.dumps(d, default=str)
                if len(preview) > 600:
                    preview = preview[:600] + "…"
                print(f"     [{j}] {preview}")

        print("-" * 80, flush=True)

    total_ms = (time.perf_counter() - total_start) * 1000
    print(f"[summary] pipeline prepared in {nice_ms(total_ms)}")

    if args.stream_batch and args.stream_batch > 0:
        print("[final] streaming full results…")
        stream_results(coll, pipeline, args.allow_disk_use, args.stream_batch)
    else:
        print("[final] run full pipeline once (no streaming preview)…")
        t0 = time.perf_counter()
        try:
            cur = coll.aggregate(pipeline, allowDiskUse=args.allow_disk_use)
            first = next(cur, None)
            ms = (time.perf_counter() - t0) * 1000
            print(f"  ↳ first result fetched in {nice_ms(ms)}")
            if first:
                preview = json.dumps(first, default=str)
                if len(preview) > 600:
                    preview = preview[:600] + "…"
                print(f"  ↳ first doc preview: {preview}")
            cur.close()
        except errors.PyMongoError:
            print("[error] running final pipeline:")
            traceback.print_exc()

if __name__ == "__main__":
    main()
