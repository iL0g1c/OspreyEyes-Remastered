import time
from pymongo import MongoClient, UpdateOne, InsertOne, DeleteOne
import os
import sys
from dotenv import load_dotenv
from urllib.parse import unquote
from datetime import datetime, timedelta
import numpy as np
import requests
import queue
import threading
import logging
import math
import re
import tracemalloc
from MongoBatchProcessor import MongoBatchProcessor

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared import multiplayerAPI, mapAPI

tracemalloc.start()

class DataCollectionLayer():
    def __init__(self):
        # sets up logger
        self.logger = self.setup_logger()
        self.systemLogs.log(10, "Initializing data collection layer...")

        # gets envs
        load_dotenv()
        self.load_environment_variables()
        self.mongo_db_client = MongoClient(self.get_mongo_uri())
        db = self.mongo_db_client[self.DATABASE_NAME]

        self.current_chat_messages = []
        self.current_online_users = []

        # sets up APIs
        self.multiplayer_api = multiplayerAPI.MultiplayerAPI(self.SESSION_ID, self.ACCOUNT_ID)
        self.mapAPI = mapAPI.MapAPI()
        self.mapAPI.disableResponseList()

        self.setup_batch_processors(db)

        self.remove_duplicate_users(initial_cleanup=True)
        db["users"].create_index("accountID", unique=True)

        self.systemLogs.log(10, "Setting up queues and threads...")
        self.setup_queues_and_threads()
        self.last_aircraft_distribution_time = datetime.now()

        self.systemLogs.log(10, "Getting configuration settings...")
        self.config = self.getConfigurationSettings()
        
        self.MAX_REQUESTS = 10

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
        if not os.path.exists("../../logs"):
            os.makedirs("../../logs")

        # teleportation event
        self.teleportationLogs = logging.getLogger("teleportation")
        self.teleportationLogs.setLevel(logging.INFO)
        teleportationHandler = logging.FileHandler("../../logs/teleportation.log")
        teleportationFormatter = logging.Formatter("%(asctime)s - %(message)s")
        teleportationHandler.setFormatter(teleportationFormatter)
        self.teleportationLogs.addHandler(teleportationHandler)

        # aircraft change event
        self.aircraftChangeLogs = logging.getLogger("aircraft-change")
        self.aircraftChangeLogs.setLevel(logging.INFO)
        aircraftChangeHandler = logging.FileHandler("../../logs/aircraft-change.log")
        aircraftChangeFormatter = logging.Formatter("%(asctime)s - %(message)s")
        aircraftChangeHandler.setFormatter(aircraftChangeFormatter)
        self.aircraftChangeLogs.addHandler(aircraftChangeHandler)

        # callsign change event
        self.callsignChangeLogs = logging.getLogger("callsign-change")
        self.callsignChangeLogs.setLevel(logging.INFO)
        callsignChangeHandler = logging.FileHandler("../../logs/callsign-change.log")
        callsignChangeFormatter = logging.Formatter("%(asctime)s - %(message)s")
        callsignChangeHandler.setFormatter(callsignChangeFormatter)
        self.callsignChangeLogs.addHandler(callsignChangeHandler)

        # new account event
        self.newAccountLogs = logging.getLogger("new-account")
        self.newAccountLogs.setLevel(logging.INFO)
        newAccountHandler = logging.FileHandler("../../logs/new-account.log")
        newAccountFormatter = logging.Formatter("%(asctime)s - %(message)s")
        newAccountHandler.setFormatter(newAccountFormatter)
        self.newAccountLogs.addHandler(newAccountHandler)

        # offline-online event
        self.offlineOnlineLogs = logging.getLogger("offline-online")
        self.offlineOnlineLogs.setLevel(logging.INFO)
        offlineOnlineHandler = logging.FileHandler("../../logs/offline-online.log")
        offlineOnlineFormatter = logging.Formatter("%(asctime)s - %(message)s")
        offlineOnlineHandler.setFormatter(offlineOnlineFormatter)
        self.offlineOnlineLogs.addHandler(offlineOnlineHandler)

        # server events
        self.systemLogs = logging.getLogger("server-events")
        self.systemLogs.setLevel(logging.ERROR)
        systemHandler = logging.FileHandler("../../logs/server-events.log")
        systemFormatter = logging.Formatter("%(asctime)s - %(message)s")
        systemHandler.setFormatter(systemFormatter)
        self.systemLogs.addHandler(systemHandler)
    
    def load_environment_variables(self):
        self.SESSION_ID = os.getenv('GEOFS_SESSION_ID')
        self.ACCOUNT_ID = os.getenv('GEOFS_ACCOUNT_ID')
        self.DATABASE_NAME = os.getenv('DATABASE_NAME')
        self.DATABASE_IP = os.getenv('DATABASE_IP')
        self.DATABASE_USER = os.getenv('DATABASE_USER')

    def get_mongo_uri(self):
        DATABASE_TOKEN = os.getenv('DATABASE_TOKEN')
        connection_string = f"mongodb://{self.DATABASE_USER}:{DATABASE_TOKEN}@{self.DATABASE_IP}:27017/?directConnection=true&serverSelectionTimeoutMS=2000&authSource={self.DATABASE_NAME}"
        print(connection_string)
        return connection_string
        
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
                self.systemLogs.log(40, f"Error processing {queue_name} queue: {e}")
                time.sleep(30 / self.MAX_REQUESTS)

    def send_batch(self, batch, session):
        try:
            response = session.post(
                batch[0]["url"],
                json=[req["data"] for req in batch]
            )
            if response.status_code != 204:
                self.systemLogs.log(30, f"Batch send failed. Status code: {response.status_code}")
        except Exception as e:
            self.systemLogs.log(40, f"Batch send failed. Error: {e}")

    def check_chat_messages_for_mention(self):
        for message in self.current_chat_messages:
            for item in ["mindseye", "minds eye", "minds-eye"]:
                if  item in message["msg"].lower():
                    url = f"http://localhost:5001/bot-mention"
                    data = {"message": True}
                    self.systemLogs.log(20, "Detected pilot mentioned bot.")
                    try:
                        response = requests.post(url, json=data)
                    except Exception as e:
                        self.systemLogs.log(40, f"Failed to trigger event. Error: {e}")

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
        if None in (old_lat, old_lon, new_lat, new_lon):
            return 0
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
                    self.offlineOnlineLogs.log(20, f"Account ID: {user['accountID']} is patrolling for force {force}.")
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
                    self.offlineOnlineLogs.log(20, f"Account ID: {user['accountID']} is no longer patrolling for force {force}.")
                    self.batch_processors["forces"].add_to_batch(
                        UpdateOne(
                            {"callsign_filter": force, "patrols.accountID": user["accountID"], "patrols.end_time": None},
                            {"$set": {"patrols.$.end_time": datetime.now()}}
                        )
                    )
        self.batch_processors["forces"].flush_batch()

    def process_users(self):
        self.remove_duplicate_users()
        raw = self.mapAPI.getUsers(False) or []
        seen = set(); unique = []
        for u in raw:
            uid = u.userInfo['id']
            if uid and uid not in seen:
                seen.add(uid); unique.append(u)
        self.current_online_users = unique

        db = self.mongo_db_client[self.DATABASE_NAME]
        user_coll = db['users']
        configs = self.config

        # prepare existing map
        cur_ids = [u.userInfo['id'] for u in unique]
        exist_map = {d['accountID']: d for d in user_coll.find({'accountID':{'$in':cur_ids}})}

        # Handle users going offline
        going_offline = list(user_coll.find({
            'Online': True,
            'accountID': {'$nin': cur_ids}
        }))
        for doc in going_offline:
            if datetime.now() - doc['lastOnline'] > timedelta(minutes=1):
                self.offlineOnlineLogs.info(f"Account ID: {doc['accountID']} is offline.")
                evt = {'eventType':'offline', 'timestamp':doc['lastOnline']}
                self.batch_processors['users'].add_to_batch(
                    UpdateOne(
                        {'accountID':doc['accountID']},
                        {'$set':{'Online':False, 'lastOnline':datetime.now()}, '$push':{'events':evt}}
                    )
                )
                self.update_airforce_patrol_logs(False, doc, self.get_force_callsign_filters())
        # handle users going online
        going_online = list(user_coll.find({
            'Online': False,
            'accountID': {'$in': cur_ids}
        }))
        for doc in going_online:
            self.offlineOnlineLogs.info(f"Account ID: {doc['accountID']} is online.")
            evt = {'eventType':'online', 'timestamp':datetime.now()}
            self.batch_processors['users'].add_to_batch(
                UpdateOne(
                    {'accountID':doc['accountID']},
                    {'$set':{'Online':True}, '$push':{'events':evt}}
                )
            )
            self.update_airforce_patrol_logs(True, doc, self.get_force_callsign_filters())

        # Process current online users
        filters = self.get_force_callsign_filters()
        for u in unique:
            uid = u.userInfo['id']; cs = u.userInfo['callsign']; ac = u.aircraft['type']; pos = u.coordinates
            # new-account hook
            if uid not in exist_map and configs['displayNewAccounts']:
                self.queues['new_account'].put({'url':'http://localhost:5001/new-account','data':{'acid':uid,'callsign':cs}})
                self.update_airforce_patrol_logs(True, {'accountID':uid,'currentCallsign':cs}, filters)
            # event detection
            evts = []
            # teleport
            old = exist_map.get(uid, {}).get('lastPosition')
            if old:
                dist = self.calculate_aircraft_change(old[0], old[1], pos[0], pos[1])
                if dist >= 50:
                    self.teleportationLogs.info(f"Account ID: {uid} teleported {round(dist)} km.")
                    evts.append({'eventType':'teleportation','oldLatitude':old[0],'oldLongitude':old[1],'newLatitude':pos[0],'newLongitude':pos[1],'timestamp':datetime.now(),'distance':dist})
            # aircraft change
            old_ac = exist_map.get(uid, {}).get('currentAircraft')
            if configs['logAircraftChanges'] and old_ac and ac != old_ac:
                self.aircraftChangeLogs.info(f"Aircraft change: {uid} from {old_ac} to {ac}")
                evts.append({'eventType':'aircraftChange','oldAircraft':old_ac,'newAircraft':ac,'timestamp':datetime.now()})
                self.queues['aircraft_change'].put({'url':'http://localhost:5001/aircraft-change','data':{'callsign':cs,'oldAircraft':old_ac,'newAircraft':ac}})
            # callsign change
            old_cs = exist_map.get(uid, {}).get('currentCallsign')
            if old_cs and old_cs != cs:
                self.callsignChangeLogs.info(f"Callsign change: {uid} from {old_cs} to {cs}")
                evts.append({'eventType':'callsignChange','oldCallsign':old_cs,'newCallsign':cs,'timestamp':datetime.now()})
                if configs['displayCallsignChanges']:
                    self.queues['callsign_change'].put({'url':'http://localhost:5001/callsign-change','data':{'acid':uid,'oldCallsign':old_cs,'newCallsign':cs}})

            # upsert user doc
            upsert = UpdateOne(
                {'accountID':uid},
                {
                    '$setOnInsert':{'accountID':uid},
                    '$set':{'currentCallsign':cs,'currentAircraft':ac,'Online':True,'lastOnline':datetime.now(),'lastPosition':pos},
                    '$addToSet':{'pastCallsigns':cs},
                    **({'$push':{'events':{'$each':evts}}} if evts else {})
                },
                upsert=True
            )
            self.batch_processors['users'].add_to_batch(upsert)

        self.batch_processors['users'].flush_batch()

    def remove_duplicate_users(self, initial_cleanup=False):
        db = self.mongo_db_client[self.DATABASE_NAME]
        user_collection = db["users"]

        with open("removed_users.txt", "a") as f:
            pipeline = [
                {"$group": {"_id": "$accountID", "count": {"$sum": 1}, "ids": {"$push": "$_id"}}},
                {"$match": {"count": {"$gt": 1}}}
            ]
            duplicates = list(user_collection.aggregate(pipeline))

            for duplicate in duplicates:
                ids_to_check = sorted(duplicate["ids"])

                for _id in ids_to_check[1:]:
                    user = user_collection.find_one({"_id": _id})
                    if not user.get("events"):
                        f.write(f"Removed duplicate user with accountID {duplicate['_id']} and _id {_id}\n")

                        if initial_cleanup:
                            user_collection.delete_one({"_id": _id})
                        else:
                            self.batch_processors["users"].add_to_batch(DeleteOne({"_id": _id}))
                            self.systemLogs.log(20, f"Removed duplicate user with accountID {duplicate['_id']} and _id {_id}")

        if not initial_cleanup:
            self.batch_processors["users"].flush_batch()

def main():
    data_collection_layer = DataCollectionLayer()
    data_collection_layer.systemLogs.log(20, "Starting data collection layer...")
    last_snapshot_time = 1800
    last_user_count_time = time.time()

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
        "displayAircraftChanges": True,
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
                data_collection_layer.systemLogs.log(20, "Found a new configuration setting. Adding it to the database.")
                collection.update_one(
                    {"_id": configuration["_id"]},
                    {"$set": {key: value}}
                )
                configuration[key] = value
        keys_to_remove = [key for key in configuration if key not in DEFAULT_CONFIG and key != "_id"]
        if keys_to_remove:
            data_collection_layer.systemLogs.log(20, "Found old configuration settings. Removing them from the database.")
            collection.update_one(
                {"_id": configuration["_id"]},
                {"$unset": {key: "" for key in keys_to_remove}}
            )
            for key in keys_to_remove:
                del configuration[key]
    previous_configuration = configuration

    data_collection_layer.systemLogs.log(20, "Data collection layer started.")
    while True: # loops every second for api calls
        print(1)
        configuration = collection.find_one()

        for key in previous_configuration: # checks if the configuration settings have changed
            if previous_configuration[key] != configuration[key]:
                data_collection_layer.systemLogs.log(20, f"Configuration setting {key} changed to {configuration[key]}")
                previous_configuration[key] = configuration[key]
        

        if configuration["storeUsers"]:
            data_collection_layer.process_users()
            print(2)
        if configuration["saveChatMessages"]:
            data_collection_layer.fetch_chat_messages()
        if configuration["accumulateHeatMap"] and (time.time() - last_snapshot_time >= 1800):
            last_snapshot_time = time.time()
            data_collection_layer.add_player_location_snapshot()
        if configuration["countUsers"] and (time.time() - last_user_count_time >= 3600):
            data_collection_layer.add_online_player_count()
        time.sleep(1)

if __name__ == "__main__":
    main()