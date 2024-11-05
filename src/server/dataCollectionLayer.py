import time
from pymongo import MongoClient, UpdateOne
import os
import sys
from dotenv import load_dotenv
from urllib.parse import unquote
from datetime import datetime
import numpy as np
import requests
import json
import queue
import threading
import logging

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared import multiplayerAPI, mapAPI



class DataCollectionLayer():
    def __init__(self):
        # gets envs
        load_dotenv()
        self.sessionID = os.getenv('GEOFS_SESSION_ID')
        self.accountID = os.getenv('GEOFS_ACCOUNT_ID')

        logging.basicConfig(level=logging.INFO)

        self.lastAircraftDistributionTime = datetime.now()

        # initializes APIs
        self.multiplayerAPI = multiplayerAPI.MultiplayerAPI(self.sessionID, self.accountID)
        self.multiplayerAPI.handshake()
        self.mapAPI = mapAPI.MapAPI()
        self.currentChatMessages = []
        self.currentOnlineUsers = []
        self.config = self.loadConfig()
        DATABASE_TOKEN = os.getenv('DATABASE_TOKEN')
        mongodbURI = f"mongodb://adminUser:{DATABASE_TOKEN}@{self.config["mongoDBIP"]}:27017/?directConnection=true&serverSelectionTimeoutMS=2000&authSource=admin"
        self.mongoDBClient = MongoClient(mongodbURI) # sets up database client

        print("Starting queue threads...")
        self.callsignChangeQueue = queue.Queue()
        self.newAccountQueue = queue.Queue()
        self.aircraftChangeQueue = queue.Queue()
        self.maxrequests = 60
        self.callsignChangeWebhookThread = threading.Thread(target=self.callsignChangeProcesser)
        self.newAccountWebhookThread = threading.Thread(target=self.newAccountProcesser)
        self.aircraftChangeWebhookThread = threading.Thread(target=self.aircraftChangeProcesser)
        self.callsignChangeWebhookThread.daemon = True
        self.newAccountWebhookThread.daemon = True
        self.aircraftChangeWebhookThread.daemon = True
        self.callsignChangeWebhookThread.start()
        self.newAccountWebhookThread.start()
        self.aircraftChangeWebhookThread.start()

        print("Starting bot connection sessions...")
        self.callsignChangeSession = requests.Session()
        self.newAccountSession = requests.Session()

    def aircraftChangeProcesser(self):
        while True:
            if not self.aircraftChangeQueue.empty():
                requestInfo = self.aircraftChangeQueue.get()
                try:
                    response = self.callsignChangeSession.post(requestInfo["url"], json=requestInfo["data"])
                    if response.status_code == 204:
                        print(f"Requests left in aircraft change queue: {self.aircraftChangeQueue.qsize()}")
                    else:
                        logging.error(f"Failed to trigger request. Status code: {response.status_code}")
                except Exception as e:
                    logging.error(f"Failed to trigger request. Error: {e}")
                    time.sleep(30 / self.maxrequests)

    def callsignChangeProcesser(self):
        while True:
            if not self.callsignChangeQueue.empty():
                requestInfo = self.callsignChangeQueue.get()
                try:
                    response = self.callsignChangeSession.post(requestInfo["url"], json=requestInfo["data"])
                    if response.status_code == 204:
                        print(f"Requests left in callsign change queue: {self.callsignChangeQueue.qsize()}")
                    else:
                        logging.error(f"Failed to trigger request. Status code: {response.status_code}")
                except Exception as e:
                    logging.error(f"Failed to trigger request. Error: {e}")
                    time.sleep(30 / self.maxrequests)
    
    def newAccountProcesser(self):
        while True:
            if not self.newAccountQueue.empty():
                requestInfo = self.newAccountQueue.get()
                try:
                    response = self.newAccountSession.post(requestInfo["url"], json=requestInfo["data"])
                    if response.status_code == 204:
                        print(f"Requests left in new account queue: {self.newAccountQueue.qsize()}")
                    else:
                        print(f"Failed to trigger request. Status code: {response.status_code}")
                except Exception as e:
                    print(f"Failed to trigger request. Error: {e}")
                    
                    time.sleep(30 / self.maxrequests)

    def loadConfig(self):
        with open("config.json") as f:
            return json.load(f)

    def checkChatMessagesForMention(self):
        for message in self.currentChatMessages:
            for item in ["mindseye", "minds eye", "minds-eye"]:
                if  item in message["msg"].lower():
                    url = f"http://{self.config['botFlaskIP']}:{self.config["botFlaskPort"]}/bot-mention"
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

    def fetchChatMessages(self): # fetches chat messages from the multiplayer API
        self.currentChatMessages = [
            {**message, "msg": unquote(message["msg"]), "datetime": datetime.now()}
            for message in self.multiplayerAPI.getMessages()
        ]
        self.checkChatMessagesForMention()
        if self.currentChatMessages:
            db = self.mongoDBClient["OspreyEyes"]
            collection = db["chat_messages"]
            collection.insert_many(self.currentChatMessages)

    def addPlayerLocationSnapshot(self): # adds a snapshot of player locations to the database
        db = self.mongoDBClient["OspreyEyes"]
        collection = db["player_locations"]
        newLatitudes = np.array([user.coordinates[0] for user in self.currentOnlineUsers])
        newLongitudes = np.array([user.coordinates[1] for user in self.currentOnlineUsers])
        docs = [{"latitude": lat, "longitude": lon} for lat, lon in zip(newLatitudes, newLongitudes)]
        if docs:
            collection.insert_many(docs)

    def addOnlinePlayerCount(self): # adds the number of online players to the database
        db = self.mongoDBClient["OspreyEyes"]
        collection = db["online_player_count"]
        collection.insert_one({"count": len(self.currentOnlineUsers), "datetime": datetime.now()})
    
    def processUsers(self):  # fetches online users from the map API
        self.currentOnlineUsers = self.mapAPI.getUsers(None)

        db = self.mongoDBClient["OspreyEyes"]
        userCollection = db["users"]
        configurations = self.getConfigurationSettings()

        newUsers = []
        updateOperations = []
        newAccountWebhooks = []
        callsignChangeWebhooks = []
        aircraftChangeWebhooks = []
        aircraftAmounts = {}

        currentAccountIDs = [user.userInfo["id"] for user in self.currentOnlineUsers]
        existingUsersMap = {
            user["accountID"]: user
            for user in userCollection.find({"accountID": {"$in": currentAccountIDs}})
        }
        existingAircraftMap = {
            user["accountID"]: user["currentAircraft"]
            for user in userCollection.find({"accountID": {"$in": currentAccountIDs}})
        }
        for user in self.currentOnlineUsers:
            if user.aircraft["type"] in aircraftAmounts:
                aircraftAmounts[user.aircraft["type"]] += 1
            else:
                aircraftAmounts[user.aircraft["type"]] = 1

            if user.userInfo["callsign"] == "Foo":  # skips users without callsigns
                continue

            userParameters = {
                "accountID": user.userInfo["id"],
                "currentCallsign": user.userInfo["callsign"],
                "currentAircraft": user.aircraft["type"],
                "lastOnline": datetime.now()
            }

            if userParameters["accountID"] not in existingUsersMap:
                print(f"New account detected: Account ID: {user.userInfo['id']}, Callsign: {user.userInfo['callsign']}")
                newUsers.append(userParameters)

                if configurations["displayNewAccounts"]:
                    url = f"http://{self.config['botFlaskIP']}:{self.config['botFlaskPort']}/new-account"
                    requestBody = {
                        "acid": user.userInfo["id"],
                        "callsign": user.userInfo["callsign"]
                    }
                    newAccountWebhooks.append({"url": url, "data": requestBody})
            else:
                if configurations["logAircraftChanges"]:
                    if user.aircraft["type"] not in existingUsersMap[userParameters["accountID"]]["currentAircraft"]:
                        print(f"Aircraft change detected: Callsign: {user.userInfo['callsign']}, Account ID: {user.userInfo['id']}, Old Aircraft: {existingAircraftMap[userParameters['accountID']]} New Aircraft: {userParameters['currentAircraft']}")
                        url = f"http://{self.config['botFlaskIP']}:{self.config['botFlaskPort']}/aircraft-change"
                        requestBody = {
                            "callsign": user.userInfo["callsign"],
                            "newAircraft": userParameters["currentAircraft"],
                            "oldAircraft": existingAircraftMap[userParameters["accountID"]]
                        }
                        aircraftChangeWebhooks.append({"url": url, "data": requestBody})

                existingUser = existingUsersMap[userParameters["accountID"]]
                if existingUser.get("currentCallsign") != user.userInfo["callsign"]:
                    print(f"Account ID: {user.userInfo['id']} changed callsign from {existingUser['currentCallsign']} to {user.userInfo['callsign']}")
                    if configurations["displayCallsignChanges"]:
                        url = f"http://{self.config['botFlaskIP']}:{self.config['botFlaskPort']}/callsign-change"
                        requestBody = {
                            "acid": user.userInfo["id"],
                            "newCallsign": user.userInfo["callsign"],
                            "oldCallsign": existingUser["currentCallsign"]
                        }
                        callsignChangeWebhooks.append({"url": url, "data": requestBody})

            updateOperations.append(
                UpdateOne(
                    {"accountID": userParameters["accountID"]},
                    {
                        "$set": {
                            "currentCallsign": userParameters["currentCallsign"],
                            "lastOnline": datetime.now(),
                            "currentAircraft": userParameters["currentAircraft"]
                        },
                        "$addToSet": {
                            "pastCallsigns": userParameters["currentCallsign"]
                        }
                    },
                    upsert=True
                )
            )
        if newUsers:
            userCollection.insert_many(newUsers)

        if updateOperations:
            result = userCollection.bulk_write(updateOperations)

        for request in newAccountWebhooks:
            self.newAccountQueue.put(request)

        for request in callsignChangeWebhooks:
            self.callsignChangeQueue.put(request)
        
        for request in aircraftChangeWebhooks:
            self.aircraftChangeQueue.put(request)

        if configurations["logAircraftDistributions"]:
            currentTime = datetime.now()
            if (currentTime - self.lastAircraftDistributionTime).seconds >= 10:
                print("Logging aircraft distribution.")
                aircraftCollection = db["aircraft"]
                aircraftCollection.insert_one({"aircraft": aircraftAmounts, "datetime": datetime.now()})
                self.lastAircraftDistributionTime = currentTime

        
    def getConfigurationSettings(self): # gets the configuration settings from the database
        if not hasattr(self, "_cached_config"):
            db = self.mongoDBClient["OspreyEyes"]
            collection = db["configurations"]
            self._cached_config = collection.find_one()
        return self._cached_config

def main():
    print("Starting data collection layer...")
    dataCollectionLayer = DataCollectionLayer()
    lastSnapshotTime = 1800
    lastUserCountTime = 3600

    db = dataCollectionLayer.mongoDBClient["OspreyEyes"]
    collection = db["configurations"]
    configuration = collection.find_one()
    defaultConfig = {
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
        for key, value in defaultConfig.items(): # checks if the configuration settings are missing
            if key not in configuration:
                print("Found a new configuration setting. Adding it to the database.")
                collection.update_one(
                    {"_id": configuration["_id"]},
                    {"$set": {key: value}}
                )
                configuration[key] = value
        keysToRemove = [key for key in configuration if key not in defaultConfig and key != "_id"]
        if keysToRemove:
            print("Found old configuration settings. Removing them from the database.")
            collection.update_one(
                {"_id": configuration["_id"]},
                {"$unset": {key: "" for key in keysToRemove}}
            )
            for key in keysToRemove:
                del configuration[key]
    else:
        collection.insert_one(defaultConfig)
        configuration = defaultConfig
    previousConfiguration = configuration

    print("Data collection layer started.")
    while True: # loops every second for api calls
        configuration = collection.find_one()

        for key in previousConfiguration: # checks if the configuration settings have changed
            if previousConfiguration[key] != configuration[key]:
                print(f"Configuration setting {key} changed to {configuration[key]}")
                previousConfiguration[key] = configuration[key]

        if configuration["saveChatMessages"]:
            dataCollectionLayer.fetchChatMessages()
        if configuration["accumulateHeatMap"] and (time.time() - lastSnapshotTime >= 1800):
            lastSnapshotTime = time.time()
            dataCollectionLayer.addPlayerLocationSnapshot()
        if configuration["countUsers"] and (time.time() - lastUserCountTime >= 3600):
            dataCollectionLayer.addOnlinePlayerCount()
        if configuration["storeUsers"]:
            dataCollectionLayer.processUsers()
        time.sleep(1)

if __name__ == "__main__":
    main()