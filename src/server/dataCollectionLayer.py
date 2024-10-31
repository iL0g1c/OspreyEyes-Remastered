import time
from pymongo import MongoClient
from multiplayerAPI import MultiplayerAPI
from mapAPI import MapAPI
import os
from dotenv import load_dotenv
from urllib.parse import unquote
from datetime import datetime
import numpy as np


class DataCollectionLayer():
    def __init__(self):
        load_dotenv()
        self.sessionID = os.getenv('GEOFS_SESSION_ID')
        self.accountID = os.getenv('GEOFS_ACCOUNT_ID')
        self.multiplayerAPI = MultiplayerAPI(self.sessionID, self.accountID)
        self.multiplayerAPI.handshake()
        self.mapAPI = MapAPI()
        self.currentChatMessages = []
        self.currentOnlineUsers = []
        DATABASE_TOKEN = os.getenv('DATABASE_TOKEN')
        mongodbURI = f"mongodb://adminUser:{DATABASE_TOKEN}@66.179.248.17:27017/?directConnection=true&serverSelectionTimeoutMS=2000&authSource=admin"
        self.mongoDBClient = MongoClient(mongodbURI)

    def fetchChatMessages(self):
        self.currentChatMessages = [
            {**message, "msg": unquote(message["msg"]), "datetime": datetime.now()}
            for message in self.multiplayerAPI.getMessages()
        ]
        if self.currentChatMessages:
            db = self.mongoDBClient["OspreyEyes"]
            collection = db["chat_messages"]
            collection.insert_many(self.currentChatMessages)

    def addPlayerLocationSnapshot(self):
        db = self.mongoDBClient["OspreyEyes"]
        collection = db["player_locations"]
        newLatitudes = np.array([user.coordinates[0] for user in self.currentOnlineUsers])
        newLongitudes = np.array([user.coordinates[1] for user in self.currentOnlineUsers])
        docs = [{"latitude": lat, "longitude": lon} for lat, lon in zip(newLatitudes, newLongitudes)]
        if docs:
            collection.insert_many(docs)
    
    def fetchOnlineUsers(self):
        self.currentOnlineUsers = self.mapAPI.getUsers(False)       
    
    def getConfigurationSettings(self):
        db = self.mongoDBClient["OspreyEyes"]
        collection = db["configurations"]
        return collection.find_one()

def main():
    dataCollectionLayer = DataCollectionLayer()
    while True:
        db = dataCollectionLayer.mongoDBClient["OspreyEyes"]
        collection = db["configurations"]
        configuration = collection.find_one()
        if configuration == None:
            collection.insert_one({
                "saveChatMessages": False,
                "accumulateHeatMap": False,
                "fetchOnlineUsers": False
            })
        
        configuration = collection.find_one()
        if configuration["saveChatMessages"]:
            print("Fetching chat messages...")
            dataCollectionLayer.fetchChatMessages()
        if configuration["accumulateHeatMap"]:
            print("Adding player location snapshot...")
            dataCollectionLayer.addPlayerLocationSnapshot()
        if configuration["fetchOnlineUsers"]:
            print("Fetching online users...")
            dataCollectionLayer.fetchOnlineUsers()
        time.sleep(0.1)

if __name__ == "__main__":
    main()