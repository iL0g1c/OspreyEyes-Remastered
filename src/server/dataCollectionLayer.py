import time
from pymongo import MongoClient
import os
import sys
from dotenv import load_dotenv
from urllib.parse import unquote
from datetime import datetime
import numpy as np
import requests
import json

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared import multiplayerAPI, mapAPI



class DataCollectionLayer():
    def __init__(self):
        # gets envs
        load_dotenv()
        self.sessionID = os.getenv('GEOFS_SESSION_ID')
        self.accountID = os.getenv('GEOFS_ACCOUNT_ID')

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
    
    def processUsers(self): # fetches online users from the map API
        self.currentOnlineUsers = self.mapAPI.getUsers(True)
        db = self.mongoDBClient["OspreyEyes"]
        userCollection = db["users"]
        for user in self.currentOnlineUsers:
            if user.userInfo["callsign"] == "Foo": # skips users without callsigns
                continue
            existingUser = userCollection.find_one({"accountID": user.userInfo["id"]})
            if existingUser and existingUser.get("currentCallsign") != user.userInfo["callsign"]:
                print(f"Account ID: {user.userInfo["id"]} changed callsign from {existingUser["currentCallsign"]} to {user.userInfo["callsign"]}")
                url = f"http://{self.config['botFlaskIP']}:{self.config["botFlaskPort"]}/callsign-change"
                requestBody = {
                    "acid": user.userInfo["id"],
                    "newCallsign": user.userInfo["callsign"],
                    "oldCallsign": existingUser["currentCallsign"]
                }
                try:
                    response = requests.post(url, json=requestBody)
                    if response.status_code == 204:
                        print("Callsign change event successfully triggered.")
                    else:
                        print(f"Failed to trigger callsign change event. Status code: {response.status_code}")
                except Exception as e:
                    print(f"Failed to trigger event. Error: {e}")
                

            userCollection.update_one(
                {"accountID": user.userInfo["id"]},
                {
                    "$set": {
                        "currentCallsign": user.userInfo["callsign"],
                        "lastOnline": datetime.now()
                    },
                    "$addToSet": {
                        "pastCallsigns": user.userInfo["callsign"]
                    }
                },
                upsert=True
            )
    
    def getConfigurationSettings(self): # gets the configuration settings from the database
        db = self.mongoDBClient["OspreyEyes"]
        collection = db["configurations"]
        return collection.find_one()

def main():
    print("Starting data collection layer...")
    dataCollectionLayer = DataCollectionLayer()
    lastSnapshotTime = 1800
    lastUserCountTime = 3600

    db = dataCollectionLayer.mongoDBClient["OspreyEyes"]
    collection = db["configurations"]
    configuration = collection.find_one()
    if configuration == None: # initializes the configuration settings if they don't exist
        collection.insert_one({
            "saveChatMessages": False,
            "accumulateHeatMap": False,
            "storeUsers": False,
            "callsignLogChannel": None,
            "displayCallsignChanges": False,
            "countUsers": False
        })
    previousConfiguration = collection.find_one() 
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