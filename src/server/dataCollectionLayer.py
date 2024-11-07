import time
from pymongo import MongoClient, UpdateOne, InsertOne
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
import re
import cProfile
import pstats
from MongoBatchProcessor import MongoBatchProcessor

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared import multiplayerAPI, mapAPI



class DataCollectionLayer():
    def __init__(self):
        # sets up logger
        self.logger = self.setup_logger()
        self.logger.log(10, "Initializing data collection layer...")

        # gets envs
        self.logger.log(10, "Loading environment variables...")
        load_dotenv()
        self.load_environment_variables()
        self.mongo_db_client = MongoClient(self.get_mongo_uri())
        db = self.mongo_db_client[self.DATABASE_NAME]

        self.current_chat_messages = []
        self.current_online_users = []

        # sets up APIs
        self.logger.log(10, "Setting up APIs...")
        self.multiplayer_api = multiplayerAPI.MultiplayerAPI(self.SESSION_ID, self.ACCOUTN_ID)
        self.map_api = mapAPI.MapAPI()

        self.logger.log(10, "Setting up batch processors...")
        self.setup_batch_processors(db)

        self.logger.log(10, "Setting up queues and threads...")
        self.setup_queues_and_threads()
        self.last_aircraft_distribution_time = datetime.now()

        self.logger.log(10, "Getting configuration settings...")
        self.config = self.getConfigurationSettings()
        
    def setup_queues_and_threads(self):
        self.queues = {
            "callsign_change": queue.Queue(),
            "new_account": queue.Queue(),
            "aircraft_change": queue.Queue()
        }
        self.sessions = {
            "callsign_change": requests.Session(),
            "new_account": requests.Session(),
            "aircraft_change": requests.Session()
        }
        self.start_webhook_threads()

    def setup_batch_processors(self, db):
        self.batch_processors = {
            "forces": MongoBatchProcessor(db["forces"]),
            "player_locations": MongoBatchProcessor(db["player_locations"]),
            "chat_messages": MongoBatchProcessor(db["chat_messages"]),
            "users": MongoBatchProcessor(db["users"])
        }

    def getConfigurationSettings(self):
        db = self.mongo_db_client[self.DATABASE_NAME]
        collection = db["configurations"]
        config = collection.find_one()
        if config == None:
            config = self.initialize_default_config(collection)
        return config
    
    def initialize_default_config(self, collection):
        DEFAULT_CONFIG = {
            "saveChatMessages": True,
            "accumulateHeatMap": True,
            "storeUsers": True,
            "callsignChangeLogChannel": None,
            "newAccountLogChannel": None,
            "aircraftChangeLogChannel": None,
            "displayCallsignChanges": True,
            "displayNewAccounts": True,
            "countUsers": True,
            "logAircraftDistributions": True,
            "logAircraftChanges": True,
            "logMRPActivity": True,
        }
        collection.insert_one(DEFAULT_CONFIG)
        return DEFAULT_CONFIG

    def setup_logger(self):
        logger = logging.getLogger("SERVER")
        logger.setLevel(logging.DEBUG)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        logger.addHandler(console_handler)
        return logger
    
    def load_environment_variables(self):
        self.SESSION_ID = os.getenv('GEOFS_SESSION_ID')
        self.ACCOUTN_ID = os.getenv('GEOFS_ACCOUNT_ID')
        self.DATABASE_NAME = os.getenv('DATABASE_NAME')

    def get_mongo_uri(self):
        DATABASE_TOKEN = os.getenv('DATABASE_TOKEN')
        return f"mongodb://adminUser:{DATABASE_TOKEN}@66.179.248.17:27017/?directConnection=true&serverSelectionTimeoutMS=2000&authSource=admin"
        
    def start_webhook_threads(self):
        for key in self.queues:
            thread = threading.Thread(target=self.webhook_processor, args=(key,))
            thread.daemon = True
            thread.start()

    def webhook_processor(self, queue_name, batch_size=50, batch_interval=0.02, timeout=5):
        batch = []
        last_send_time = time.time()
        while True:
            try:
                if not self.queues[queue_name].empty():
                    batch.append(self.queues[queue_name].get())
                if len(batch) >= batch_size or (time.time() - last_send_time) >= timeout:
                    if batch:
                        self.send_batch(batch, self.sessions[queue_name])
                        last_send_time = time.time()
                        batch.clear()
                time.sleep(batch_interval)
            except Exception as e:
                self.logger.log(40, f"Error processing {queue_name} queue: {e}")
                time.sleep(30 / self.MAX_REQUESTS)

    def send_batch(self, batch, session):
        try:
            response = session.post(
                batch[0]["url"],
                json=[req["data"] for req in batch]
            )
            if response.status_code != 204:
                self.logger.log(30, f"Batch send failed. Status code: {response.status_code}")
        except Exception as e:
            self.logger.log(40, f"Batch send failed. Error: {e}")

    def check_chat_messages_for_mention(self):
        for message in self.current_chat_messages:
            for item in ["mindseye", "minds eye", "minds-eye"]:
                if  item in message["msg"].lower():
                    url = f"http://localhost:5001/bot-mention"
                    data = {"message": True}
                    self.logger.log(20, "Detected pilot mentioned bot.")
                    try:
                        response = requests.post(url, json=data)
                    except Exception as e:
                        self.logger.log(40, f"Failed to trigger event. Error: {e}")

    def fetch_chat_messages(self): # fetches chat messages from the multiplayer API
        self.current_chat_messages = [
            {**message, "msg": unquote(message["msg"]), "datetime": datetime.now()}
            for message in self.multiplayer_api.getMessages()
        ]
        self.check_chat_messages_for_mention()
        if self.current_chat_messages:
            for msg in self.current_chat_messages:
                self.batch_processors["chat_messages"].add_to_batch(InsertOne(msg))
        self.batch_processors["chat_messages"].flush_batch()

    def add_player_location_snapshot(self): # adds a snapshot of player locations to the database
        docs = [
            {
                "latitude": user.coordinates[0],
                "longitude": user.coordinates[1]
            } for user in self.current_online_users
        ]
        if docs:
            for doc in docs:
                self.batch_processors["player_locations"].add_to_batch(InsertOne(doc))
        self.batch_processors["player_locations"].flush_batch()

    def add_online_player_count(self): # adds the number of online players to the database
        db = self.mongo_db_client[self.DATABASE_NAME]
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
    
    def get_force_callsign_filters(self): # gets the force callsign_filters from the database
        db = self.mongo_db_client[self.DATABASE_NAME]
        collection = db["forces"]
        forces = collection.find()
        return [force["callsign_filter"] for force in forces]

    def update_airforce_patrol_logs(self, going_online, user, force_callsign_filters):

        for force in force_callsign_filters:
            regex_pattern = force.replace('[', r'\[').replace(']', r'\]').replace('X', '.')

            regex = re.compile(r".*" + regex_pattern + r".*", re.IGNORECASE)
            if regex.search(user["currentCallsign"]):
                if going_online:
                    self.logger.log(20, f"Account ID: {user['accountID']} is patrolling for force {force}.")
                    force_event = {
                        "accountID": user["accountID"],
                        "callsign": user["currentCallsign"],
                        "start_time": datetime.now(),
                        "end_time": None
                    }
                    self.batch_processors["forces"].add_to_batch(
                        UpdateOne(
                            {"callsign_filter": force},
                            {"$push": {"patrols": force_event}}
                        )
                    )
                else:
                    self.logger.log(20, f"Account ID: {user['accountID']} is no longer patrolling for force {force}.")
                    self.batch_processors["forces"].add_to_batch(
                        UpdateOne(
                            {"callsign_filter": force, "patrols.accountID": user["accountID"], "patrols.end_time": None},
                            {"$set": {"patrols.$.end_time": datetime.now()}}
                        )
                    )
        self.batch_processors["forces"].flush_batch()

    def process_users(self):
        # Fetch online users from the map API
        self.current_online_users = self.map_api.getUsers(None)
        db = self.mongo_db_client[self.DATABASE_NAME]
        user_collection = db["users"]
        configurations = self.config

        # Initialize variables for tracking new, updated, and offline users
        new_users = []
        update_operations = []
        new_account_webhooks = []
        callsign_change_webhooks = []
        aircraft_change_webhooks = []
        aircraft_amounts = {}
        force_callsign_filters = self.get_force_callsign_filters()

        current_account_ids = [user.userInfo["id"] for user in self.current_online_users]
        existing_users_map = {user["accountID"]: user for user in user_collection.find({"accountID": {"$in": current_account_ids}})}
        existing_aircraft_map = {user["accountID"]: user["currentAircraft"] for user in existing_users_map.values()}

        # Handle users going offline
        going_offline_users = list(user_collection.find({
            "Online": True,
            "accountID": {"$nin": current_account_ids}
        })) 
        for user in going_offline_users:
            # Ensure user has been offline long enough
            if datetime.now() - user["lastOnline"] > timedelta(minutes=1):
                self.logger.log(20, f"Account ID: {user['accountID']} is offline.")
                events = {
                    "eventType": "offline",
                    "timestamp": user["lastOnline"]
                }
                # Log before update
                self.batch_processors["users"].add_to_batch(
                    UpdateOne(
                        {"accountID": user["accountID"]},
                        {"$set": {"Online": False, "lastOnline": datetime.now()}, "$push": {"events": events}}
                    )
                )
                self.update_airforce_patrol_logs(False, user, force_callsign_filters)

        # Handle users going online
        going_online_users = list(user_collection.find({
            "Online": False,
            "accountID": {"$in": current_account_ids}
        }))
        for user in going_online_users:
            self.logger.log(20, f"Account ID: {user['accountID']} is online.")
            event = {
                "eventType": "online",
                "timestamp": datetime.now()
            }
            self.batch_processors["users"].add_to_batch(
                UpdateOne(
                    {"accountID": user["accountID"]},
                    {"$set": {"Online": True}, "$push": {"events": event}}
                )
            )
            self.update_airforce_patrol_logs(True, user, force_callsign_filters)    

        # Process current online users
        for user in self.current_online_users:
            if user.userInfo["callsign"] == "Foo":
                continue
            user_id = user.userInfo["id"]
            user_callsign = user.userInfo["callsign"]
            user_aircraft = user.aircraft["type"]
            user_position = user.coordinates
            user_data = {
                "accountID": user_id,
                "currentCallsign": user_callsign,
                "currentAircraft": user_aircraft,
                "Online": True,
                "lastOnline": datetime.now(),
                "lastPosition": user_position
            }

            pending_events = []

            if user_aircraft in aircraft_amounts:
                aircraft_amounts[user_aircraft] += 1
            else:
                aircraft_amounts[user_aircraft] = 1

            if user.userInfo["callsign"] == "Foo":  # skips users without callsigns
                continue

            if user_id not in existing_users_map:
                # new pilots
                self.logger.log(20, f"New account detected: Account ID: {user_callsign}, Callsign: {user_callsign}")
                user_data["events"] = []
                self.batch_processors["users"].add_to_batch(InsertOne(user_data))

                if configurations["displayNewAccounts"]:
                    url = f"http://localhost:5001/new-account"
                    request_body = {
                        "acid": user_id,
                        "callsign": user_callsign
                    }
                    new_account_webhooks.append({"url": url, "data": request_body})

                self.update_airforce_patrol_logs(True, user_data, force_callsign_filters)
            else:
                # existing user updates
                existing_user = existing_users_map[user_id]
                pending_events = []

                # check for teleportation
                distance = self.calculate_aircraft_change( 
                    existing_user["lastPosition"][0],
                    existing_user["lastPosition"][1],
                    user_data["lastPosition"][0],
                    user_data["lastPosition"][1]
                )
                if distance >= 50:
                    self.logger.log(20, f"Account ID: {user_id} teleported {distance} km.")
                    teleportation_event = {
                        "eventType": "teleportation",
                        "oldLatittude": existing_user["lastPosition"][0],
                        "oldLongitude": existing_user["lastPosition"][1],
                        "newLatitude": user_position[0],
                        "newLongitude": user_position[1],
                        "timestamp": datetime.now(),
                        "distance": distance
                    }
                    pending_events.append(teleportation_event)
                    
                # check for aircraft changes
                if configurations["logAircraftChanges"] and user_aircraft !=  existing_aircraft_map[user_id]:
                    self.logger.log(20, f"Aircraft change detected: Callsign: {user_callsign}, Account ID: {user_id}, Old Aircraft: {existing_aircraft_map[user_id]} New Aircraft: {user_aircraft}")
                    aircraft_change_event = {
                        "eventType": "aircraftChange",
                        "timestamp": datetime.now(),
                        "newAircraft": user_aircraft,
                        "oldAircraft": existing_aircraft_map[user_id],
                    }
                    pending_events.append(aircraft_change_event)
                    url = f"http://localhost:5001/aircraft-change"
                    request_body = {
                        "callsign": user.userInfo["callsign"],
                        "newAircraft": user_aircraft,
                        "oldAircraft": existing_aircraft_map[user_id]
                    }
                    aircraft_change_webhooks.append({"url": url, "data": request_body})
                # check for callsign changes
                if existing_user.get("currentCallsign") != user.userInfo["callsign"]:
                    self.logger.log(20, f"Account ID: {user_id} changed callsign from {existing_user['currentCallsign']} to {user_callsign}")
                    callsign_change_event = {
                        "eventType": "callsignChange",
                        "timestamp": datetime.now(),
                        "newCallsign": user_callsign,
                        "oldCallsign": existing_user["currentCallsign"]
                    }
                    pending_events.append(callsign_change_event)
                    if configurations["displayCallsignChanges"]:
                        url = f"http://localhost:5001/callsign-change"
                        request_body = {
                            "acid": user_id,
                            "newCallsign": user_callsign,
                            "oldCallsign": existing_user["currentCallsign"]
                        }
                        callsign_change_webhooks.append({"url": url, "data": request_body})

            update_data = {
                "$set": {
                    "currentCallsign": user_callsign,
                    "currentAircraft": user_aircraft,
                    "lastOnline": datetime.now(),
                    "lastPosition": user_position
                },
                "$addToSet": {
                    "pastCallsigns": user_callsign
                }
            }
            if pending_events:
                update_data["$push"] = {"events": {"$each": pending_events}}

            self.batch_processors["users"].add_to_batch(
                UpdateOne(
                    {"accountID": user_id},
                    update_data,
                    upsert=True
                )
            )

        for request in new_account_webhooks:
            self.queues["new_account"].put(request)

        for request in callsign_change_webhooks:
            self.queues["callsign_change"].put(request)
        
        for request in aircraft_change_webhooks:
            self.queues["aircraft_change"].put(request)

        if configurations["logAircraftDistributions"]:
            current_time = datetime.now()
            if (current_time - self.last_aircraft_distribution_time).seconds >= 3600:
                self.logger.log(20, "Logging aircraft distribution.")
                aircraft_collection = db["aircraft"]
                aircraft_collection.insert_one({"aircraft": aircraft_amounts, "datetime": datetime.now()})
                self.last_aircraft_distribution_time = current_time

        self.batch_processors["users"].flush_batch()
        self.batch_processors["forces"].flush_batch()

        
    def getConfigurationSettings(self): # gets the configuration settings from the database
        if not hasattr(self, "_cached_config"):
            db = self.mongo_db_client[self.DATABASE_NAME]
            collection = db["configurations"]
            self._cached_config = collection.find_one()
        return self._cached_config

def main(profiler):
    data_collection_layer = DataCollectionLayer()
    data_collection_layer.logger.log(20, "Starting data collection layer...")
    last_snapshot_time = 1800
    last_user_count_time = 3600

    db = data_collection_layer.mongo_db_client[data_collection_layer.DATABASE_NAME]
    collection = db["configurations"]
    configuration = collection.find_one()
    DEFAULT_CONFIG = {
        "saveChatMessages": True,
        "accumulateHeatMap": True,
        "storeUsers": True,
        "callsignChangeLogChannel": None,
        "newAccountLogChannel": None,
        "aircraftChangeLogChannel": None,
        "displayCallsignChanges": True,
        "displayNewAccounts": True,
        "countUsers": True,
        "logAircraftDistributions": True,
        "logAircraftChanges": True,
        "logMRPActivity": True,
    }

    if configuration is None:
        collection.insert_one(DEFAULT_CONFIG)
    else: # checks if the configuration settings exist
        for key, value in DEFAULT_CONFIG.items(): # checks if the configuration settings are missing
            if key not in configuration:
                data_collection_layer.logger.log(20, "Found a new configuration setting. Adding it to the database.")
                collection.update_one(
                    {"_id": configuration["_id"]},
                    {"$set": {key: value}}
                )
                configuration[key] = value
        keys_to_remove = [key for key in configuration if key not in DEFAULT_CONFIG and key != "_id"]
        if keys_to_remove:
            data_collection_layer.logger.log(20, "Found old configuration settings. Removing them from the database.")
            collection.update_one(
                {"_id": configuration["_id"]},
                {"$unset": {key: "" for key in keys_to_remove}}
            )
            for key in keys_to_remove:
                del configuration[key]
    previous_configuration = configuration

    data_collection_layer.logger.log(20, "Data collection layer started.")
    try:
        while True: # loops every second for api calls
            configuration = collection.find_one()

            for key in previous_configuration: # checks if the configuration settings have changed
                if previous_configuration[key] != configuration[key]:
                    data_collection_layer.logger.log(20, f"Configuration setting {key} changed to {configuration[key]}")
                    previous_configuration[key] = configuration[key]
            

            if configuration["storeUsers"]:
                data_collection_layer.process_users()
            if configuration["saveChatMessages"]:
                data_collection_layer.fetch_chat_messages()
            if configuration["accumulateHeatMap"] and (time.time() - last_snapshot_time >= 1800):
                last_snapshot_time = time.time()
                data_collection_layer.add_player_location_snapshot()
            if configuration["countUsers"] and (time.time() - last_user_count_time >= 3600):
                data_collection_layer.add_online_player_count()
            time.sleep(1)
    except KeyboardInterrupt:
        print("Aborted by user. Printing profiling stats...")
        profiler.disable()
        profiler.dump_stats("dataCollectionLayer.prof")

        with open("results.txt", "w") as f:
            stats = pstats.Stats(profiler, stream=f).sort_stats("cumulative")
            stats.print_stats(20)
        print("Profiling stats printed to results.txt.")

if __name__ == "__main__":
    profiler = cProfile.Profile()
    profiler.enable()
    main(profiler)