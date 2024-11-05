import time
from pymongo import MongoClient, UpdateOne
import os
import sys
from dotenv import load_dotenv
from urllib.parse import unquote
from datetime import datetime, timedelta
import numpy as np
import requests
import json
import queue
import threading
import logging
import math

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared import multiplayerAPI, mapAPI



class DataCollectionLayer():
    def __init__(self):
        # gets envs
        load_dotenv()
        self.SESSION_ID = os.getenv('GEOFS_SESSION_ID')
        self.ACCOUTN_ID = os.getenv('GEOFS_ACCOUNT_ID')

        logging.basicConfig(level=logging.INFO)

        self.last_aircraft_distribution_time = datetime.now()

        # initializes APIs
        self.multiplayer_api = multiplayerAPI.MultiplayerAPI(self.SESSION_ID, self.ACCOUTN_ID)
        self.multiplayer_api.handshake()
        self.map_api = mapAPI.MapAPI()
        self.current_chat_messages = []
        self.current_online_users = []
        self.config = self.load_config()
        DATABASE_TOKEN = os.getenv('DATABASE_TOKEN')
        MONGODB_URI = f"mongodb://adminUser:{DATABASE_TOKEN}@{self.config['mongoDBIP']}:27017/?directConnection=true&serverSelectionTimeoutMS=2000&authSource=admin"
        self.mongo_db_client = MongoClient(MONGODB_URI) # sets up database client

        print("Starting queue threads...")
        self.callsign_change_queue = queue.Queue()
        self.new_account_queue = queue.Queue()
        self.aircraft_change_queue = queue.Queue()
        self.MAX_REQUESTS = 60
        self.callsign_change_webhook_thread = threading.Thread(target=self.callsign_change_processor)
        self.new_account_webhook_thread = threading.Thread(target=self.new_account_processor)
        self.aircraft_change_webhook_thread = threading.Thread(target=self.aircraft_change_processor)
        self.callsign_change_webhook_thread.daemon = True
        self.new_account_webhook_thread.daemon = True
        self.aircraft_change_webhook_thread.daemon = True
        self.callsign_change_webhook_thread.start()
        self.new_account_webhook_thread.start()
        self.aircraft_change_webhook_thread.start()

        print("Starting bot connection sessions...")
        self.callsign_change_session = requests.Session()
        self.new_account_session = requests.Session()

    def aircraft_change_processor(self):
        while True:
            if not self.aircraft_change_queue.empty():
                request_info = self.aircraft_change_queue.get()
                try:
                    response = self.callsign_change_session.post(request_info["url"], json=request_info["data"])
                    if response.status_code == 204:
                        print(f"Requests left in aircraft change queue: {self.aircraft_change_queue.qsize()}")
                    else:
                        logging.error(f"Failed to trigger request. Status code: {response.status_code}")
                except Exception as e:
                    logging.error(f"Failed to trigger request. Error: {e}")
                    time.sleep(30 / self.MAX_REQUESTS)

    def callsign_change_processor(self):
        while True:
            if not self.callsign_change_queue.empty():
                request_info = self.callsign_change_queue.get()
                try:
                    response = self.callsign_change_session.post(request_info["url"], json=request_info["data"])
                    if response.status_code == 204:
                        print(f"Requests left in callsign change queue: {self.callsign_change_queue.qsize()}")
                    else:
                        logging.error(f"Failed to trigger request. Status code: {response.status_code}")
                except Exception as e:
                    logging.error(f"Failed to trigger request. Error: {e}")
                    time.sleep(30 / self.MAX_REQUESTS)
    
    def new_account_processor(self):
        while True:
            if not self.new_account_queue.empty():
                request_info = self.new_account_queue.get()
                try:
                    response = self.new_account_session.post(request_info["url"], json=request_info["data"])
                    if response.status_code == 204:
                        print(f"Requests left in new account queue: {self.new_account_queue.qsize()}")
                    else:
                        print(f"Failed to trigger request. Status code: {response.status_code}")
                except Exception as e:
                    print(f"Failed to trigger request. Error: {e}")
                    
                    time.sleep(30 / self.MAX_REQUESTS)

    def load_config(self):
        with open("config.json") as f:
            return json.load(f)

    def check_chat_messages_for_mention(self):
        for message in self.current_chat_messages:
            for item in ["mindseye", "minds eye", "minds-eye"]:
                if  item in message["msg"].lower():
                    url = f"http://{self.config['botFlaskIP']}:{self.config['botFlaskPort']}/bot-mention"
                    data = {"message": True}
                    print("Detected pilot mentioned bot.")
                    try:
                        response = requests.post(url, json=data)
                        if response.status_code == 204:\
                            print("Mention event successfully triggered.")
                        else:
                            print(f"Failed to trigger mention event. Status code: {response.status_code}")
                    except Exception as e:
                        print(f"Failed to trigger event. Error: {e}")

    def fetch_chat_messages(self): # fetches chat messages from the multiplayer API
        self.current_chat_messages = [
            {**message, "msg": unquote(message["msg"]), "datetime": datetime.now()}
            for message in self.multiplayer_api.getMessages()
        ]
        self.check_chat_messages_for_mention()
        if self.current_chat_messages:
            db = self.mongo_db_client["OspreyEyes"]
            collection = db["chat_messages"]
            collection.insert_many(self.current_chat_messages)

    def add_player_location_snapshot(self): # adds a snapshot of player locations to the database
        db = self.mongo_db_client["OspreyEyes"]
        collection = db["player_locations"]
        new_latitudes = np.array([user.coordinates[0] for user in self.current_online_users])
        new_longitudes = np.array([user.coordinates[1] for user in self.current_online_users])
        docs = [{"latitude": lat, "longitude": lon} for lat, lon in zip(new_latitudes, new_longitudes)]
        if docs:
            collection.insert_many(docs)

    def add_online_player_count(self): # adds the number of online players to the database
        db = self.mongo_db_client["OspreyEyes"]
        collection = db["online_player_count"]
        collection.insert_one({"count": len(self.current_online_users), "datetime": datetime.now()})
    
    def calculate_aircraft_change(self, old_lat, old_lon, new_lat, new_lon): # calculates the distance between the old and new pilot position
        # convert points to radians
        lon1, lat1, lon2, lat2 = map(math.radians, [old_lon, old_lat, new_lon, new_lat])

        # harversine formula
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

        # radius of earth
        R = 6371
        return c * R
    
    def process_users(self):  # fetches online users from the map API
        self.current_online_users = self.map_api.getUsers(None)

        db = self.mongo_db_client["OspreyEyes"]
        user_collection = db["users"]
        configurations = self.getConfigurationSettings()

        new_users = []
        update_operations = []
        new_account_webhooks = []
        callsign_change_webhooks = []
        aircraft_change_webhooks = []
        aircraft_amounts = {}

        current_account_ids = [user.userInfo["id"] for user in self.current_online_users]
        existing_users_map = {
            user["accountID"]: user
            for user in user_collection.find({"accountID": {"$in": current_account_ids}})
        }
        existing_aircraft_map = {
            user["accountID"]: user["currentAircraft"]
            for user in user_collection.find({"accountID": {"$in": current_account_ids}})
        }

        # Handle users going offline
        going_offline_users = list(user_collection.find({
            "Online": True,
            "accountID": {"$nin": current_account_ids}
        }))
        for user in going_offline_users:
            # Ensure user has been offline long enough
            if datetime.now() - user["lastOnline"] > timedelta(minutes=1):
                print(f"Account ID: {user['accountID']} is offline.")
                events = {
                    "eventType": "offline",
                    "timestamp": user["lastOnline"]
                }
                # Log before update
                logging.info(f"Updating accountID {user['accountID']} to offline and adding offline event.")
                update_operations.append(
                    UpdateOne(
                        {"accountID": user["accountID"]},
                        {"$set": {"Online": False, "lastOnline": datetime.now()}, "$push": {"events": events}}
                    )
                )

        # Handle users going online
        going_online_users = list(user_collection.find({
            "Online": False,
            "accountID": {"$in": current_account_ids}
        }))
        for user in going_online_users:
            print(f"Account ID: {user['accountID']} is online.")
            event = {
                "eventType": "online",
                "timestamp": datetime.now()
            }
            logging.info(f"Updating accountID {user['accountID']} to online and adding online event.")
            update_operations.append(
                UpdateOne(
                    {"accountID": user["accountID"]},
                    {"$set": {"Online": True}, "$push": {"events": event}}
                )
            )
        
        for user in self.current_online_users:
            pending_events = []
            if user.aircraft["type"] in aircraft_amounts:
                aircraft_amounts[user.aircraft["type"]] += 1
            else:
                aircraft_amounts[user.aircraft["type"]] = 1

            if user.userInfo["callsign"] == "Foo":  # skips users without callsigns
                continue

            user_parameters = {
                "accountID": user.userInfo["id"],
                "currentCallsign": user.userInfo["callsign"],
                "currentAircraft": user.aircraft["type"],
                "Online": True,
                "lastOnline": datetime.now(),
                "lastPosition": user.coordinates,
            }

            if user_parameters["accountID"] not in existing_users_map:
                print(f"New account detected: Account ID: {user.userInfo['id']}, Callsign: {user.userInfo['callsign']}")
                user_parameters["events"] = []
                new_users.append(user_parameters)

                if configurations["displayNewAccounts"]:
                    url = f"http://{self.config['botFlaskIP']}:{self.config['botFlaskPort']}/new-account"
                    request_body = {
                        "acid": user.userInfo["id"],
                        "callsign": user.userInfo["callsign"]
                    }
                    new_account_webhooks.append({"url": url, "data": request_body})
            else:
                distance = self.calculate_aircraft_change(
                    existing_users_map[user_parameters["accountID"]]["lastPosition"][0],
                    existing_users_map[user_parameters["accountID"]]["lastPosition"][1],
                    user_parameters["lastPosition"][0],
                    user_parameters["lastPosition"][1]
                )
                if distance >= 50:
                    print(f"Account ID: {user.userInfo['id']} teleported {distance} km.")
                    teleportation_event = {
                        "eventType": "teleportation",
                        "oldLatittude": existing_users_map[user_parameters["accountID"]]["lastPosition"][0],
                        "oldLongitude": existing_users_map[user_parameters["accountID"]]["lastPosition"][1],
                        "newLatitude": user_parameters["lastPosition"][0],
                        "newLongitude": user_parameters["lastPosition"][1],
                        "timestamp": datetime.now(),
                        "distance": distance
                    }
                    pending_events.append(teleportation_event)
                if configurations["logAircraftChanges"]:
                    if user.aircraft["type"] not in existing_users_map[user_parameters["accountID"]]["currentAircraft"]:
                        print(f"Aircraft change detected: Callsign: {user.userInfo['callsign']}, Account ID: {user.userInfo['id']}, Old Aircraft: {existing_aircraft_map[user_parameters['accountID']]} New Aircraft: {user_parameters['currentAircraft']}")
                        aircraft_change_event = {
                            "eventType": "aircraftChange",
                            "timestamp": datetime.now(),
                            "newAircraft": user_parameters["currentAircraft"],
                            "oldAircraft": existing_aircraft_map[user_parameters["accountID"]],
                        }
                        pending_events.append(aircraft_change_event)
                        url = f"http://{self.config['botFlaskIP']}:{self.config['botFlaskPort']}/aircraft-change"
                        request_body = {
                            "callsign": user.userInfo["callsign"],
                            "newAircraft": user_parameters["currentAircraft"],
                            "oldAircraft": existing_aircraft_map[user_parameters["accountID"]]
                        }
                        aircraft_change_webhooks.append({"url": url, "data": request_body})

                existing_user = existing_users_map[user_parameters["accountID"]]
                if existing_user.get("currentCallsign") != user.userInfo["callsign"]:
                    print(f"Account ID: {user.userInfo['id']} changed callsign from {existing_user['currentCallsign']} to {user.userInfo['callsign']}")
                    callsign_change_event = {
                        "eventType": "callsignChange",
                        "timestamp": datetime.now(),
                        "newCallsign": user.userInfo["callsign"],
                        "oldCallsign": existing_user["currentCallsign"]
                    }
                    pending_events.append(callsign_change_event)
                    if configurations["displayCallsignChanges"]:
                        url = f"http://{self.config['botFlaskIP']}:{self.config['botFlaskPort']}/callsign-change"
                        request_body = {
                            "acid": user.userInfo["id"],
                            "newCallsign": user.userInfo["callsign"],
                            "oldCallsign": existing_user["currentCallsign"]
                        }
                        callsign_change_webhooks.append({"url": url, "data": request_body})

            update_data = {
                "$set": {
                    "currentCallsign": user_parameters["currentCallsign"],
                    "currentAircraft": user_parameters["currentAircraft"],
                    "lastOnline": user_parameters["lastOnline"],
                    "lastPosition": user_parameters["lastPosition"]
                },
                "$addToSet": {
                    "pastCallsigns": user_parameters["currentCallsign"]
                }
            }
            for event in pending_events:
                update_data["$push"] = {"events": event}

            update_operations.append(
                UpdateOne(
                    {"accountID": user_parameters["accountID"]},
                    update_data,
                    upsert=True
                )
            )
        if new_users:
            user_collection.insert_many(new_users)

        if update_operations:
            result = user_collection.bulk_write(update_operations)

        for request in new_account_webhooks:
            self.new_account_queue.put(request)

        for request in callsign_change_webhooks:
            self.callsign_change_queue.put(request)
        
        for request in aircraft_change_webhooks:
            self.aircraft_change_queue.put(request)

        if configurations["logAircraftDistributions"]:
            current_time = datetime.now()
            if (current_time - self.last_aircraft_distribution_time).seconds >= 3600:
                print("Logging aircraft distribution.")
                aircraft_collection = db["aircraft"]
                aircraft_collection.insert_one({"aircraft": aircraft_amounts, "datetime": datetime.now()})
                self.last_aircraft_distribution_time = current_time

        
    def getConfigurationSettings(self): # gets the configuration settings from the database
        if not hasattr(self, "_cached_config"):
            db = self.mongo_db_client["OspreyEyes"]
            collection = db["configurations"]
            self._cached_config = collection.find_one()
        return self._cached_config

def main():
    print("Starting data collection layer...")
    data_collection_layer = DataCollectionLayer()
    last_snapshot_time = 1800
    last_user_count_time = 3600

    db = data_collection_layer.mongo_db_client["OspreyEyes"]
    collection = db["configurations"]
    configuration = collection.find_one()
    DEFAULT_CONFIG = {
        "saveChatMessages": False,
        "accumulateHeatMap": False,
        "storeUsers": False,
        "callsignChangeLogChannel": None,
        "newAccountLogChannel": None,
        "aircraftChangeLogChannel": None,
        "displayCallsignChanges": False,
        "displayNewAccounts": False,
        "countUsers": False,
        "logAircraftDistributions": False,
        "logAircraftChanges": False,
    }
    if configuration: # checks if the configuration settings exist
        for key, value in DEFAULT_CONFIG.items(): # checks if the configuration settings are missing
            if key not in configuration:
                print("Found a new configuration setting. Adding it to the database.")
                collection.update_one(
                    {"_id": configuration["_id"]},
                    {"$set": {key: value}}
                )
                configuration[key] = value
        keys_to_remove = [key for key in configuration if key not in DEFAULT_CONFIG and key != "_id"]
        if keys_to_remove:
            print("Found old configuration settings. Removing them from the database.")
            collection.update_one(
                {"_id": configuration["_id"]},
                {"$unset": {key: "" for key in keys_to_remove}}
            )
            for key in keys_to_remove:
                del configuration[key]
    else:
        collection.insert_one(DEFAULT_CONFIG)
        configuration = DEFAULT_CONFIG
    previous_configuration = configuration

    print("Data collection layer started.")
    while True: # loops every second for api calls
        configuration = collection.find_one()

        for key in previous_configuration: # checks if the configuration settings have changed
            if previous_configuration[key] != configuration[key]:
                print(f"Configuration setting {key} changed to {configuration[key]}")
                previous_configuration[key] = configuration[key]

        if configuration["saveChatMessages"]:
            data_collection_layer.fetch_chat_messages()
        if configuration["accumulateHeatMap"] and (time.time() - last_snapshot_time >= 1800):
            last_snapshot_time = time.time()
            data_collection_layer.add_player_location_snapshot()
        if configuration["countUsers"] and (time.time() - last_user_count_time >= 3600):
            data_collection_layer.add_online_player_count()
        if configuration["storeUsers"]:
            data_collection_layer.process_users()
        time.sleep(1)

if __name__ == "__main__":
    main()