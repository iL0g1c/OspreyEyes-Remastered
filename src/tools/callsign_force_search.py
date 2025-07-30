import os
import argparse
from datetime import datetime, timedelta
from pprint import pprint
from pymongo import MongoClient
from dotenv import load_dotenv
from bson import json_util
import json



def get_database():
    load_dotenv()
    db_user = os.getenv("DATABASE_USER")
    db_token = os.getenv("DATABASE_TOKEN")
    db_ip = os.getenv("DATABASE_IP")
    db_name = os.getenv("DATABASE_NAME")
    if not all([db_user, db_token, db_ip, db_name]):
        raise RuntimeError("Database environment variables are not fully set")
    uri = (
        f"mongodb://{db_user}:{db_token}@{db_ip}:27017/"
        f"?directConnection=true&serverSelectionTimeoutMS=2000&authSource={db_name}"
    )
    client = MongoClient(uri)
    return client[db_name]


def build_pipeline(usaf_days: int, other_days: int):
    now = datetime.utcnow()
    usaf_start = now - timedelta(days=usaf_days)
    other_start = now - timedelta(days=other_days)

    usaf_regex = r"(\[[^\]]{2}\]\[[^\]]{3}\]\[USAF\])|(\[[^\]]{3}\]\[[^\]]{3}\]\[USAF\])"
    other_regex = r"\[(FAA|IAF|RNZAF|UAC|UAEAF|RAF|CAAF|IMFC)\]"

    pipeline = [
        {
            "$addFields": {
                "usaf_events": {
                    "$filter": {
                        "input": "$events",
                        "as": "e",
                        "cond": {
                            "$and": [
                                {"$eq": ["$$e.eventType", "callsignChange"]},
                                {"$regexMatch": {"input": "$$e.newCallsign", "regex": usaf_regex, "options": "i"}},
                                {"$gte": ["$$e.timestamp", usaf_start]},
                            ]
                        },
                    }
                },
                "other_events": {
                    "$filter": {
                        "input": "$events",
                        "as": "e",
                        "cond": {
                            "$and": [
                                {"$eq": ["$$e.eventType", "callsignChange"]},
                                {"$regexMatch": {"input": "$$e.newCallsign", "regex": other_regex, "options": "i"}},
                                {"$gte": ["$$e.timestamp", other_start]},
                            ]
                        },
                    }
                },
            }
        },
        {"$match": {"usaf_events.0": {"$exists": True}}},
        {"$addFields": {"has_other_codes": {"$gt": [{"$size": "$other_events"}, 0]}}},
        {"$project": {"usaf_events": 0, "other_events": 0}}
    ]
    return pipeline


def main():
    parser = argparse.ArgumentParser(description="Find users with specific callsign history")
    parser.add_argument("usaf_days", type=int, help="Days to look back for USAF callsigns")
    parser.add_argument(
        "other_days",
        type=int,
        help="Days to look back for other force callsigns",
    )
    args = parser.parse_args()

    db = get_database()
    pipeline = build_pipeline(args.usaf_days, args.other_days)
    results = list(db["users"].aggregate(pipeline))

    print(f"Found {len(results)} hit(s) in the last {args.usaf_days} days.")
    processed_json = []
    for user in results:
        user_data = {
            "user_id": user["_id"],
            "account_id": user["accountID"],
            "current_callsign": user["currentCallsign"],
            "last_online": user["lastOnline"],
            "past_callsigns": user["pastCallsigns"],
        }
        processed_json.append(user_data)
    with open("output.json", "w") as f:
        json.dump(json.loads(json_util.dumps(processed_json)), f, indent=4)


if __name__ == "__main__":
    main()