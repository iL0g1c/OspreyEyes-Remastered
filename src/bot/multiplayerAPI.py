import requests
import json
import time
import traceback


class MultiplayerAPI:
    def __init__(self, sessionID, accountID):
        self.sessionID = sessionID
        self.accountID = accountID
        self.myID = None,
        self.lastMsgID = None,
    
    def handshake(self): # initializes connection and gains mandatory variables from server.
        # initializes server connection and gets details from server.
        while True:
            body = {
                "origin": "https://www.geo-fs.com",
                "acid": self.accountID,
                "sid": self.sessionID,
                "id": "",
                "ac": "1",
                "co": [9999999999999999,9999999999999999,999999999999999,9999999999999999,999999999999999,999999999999999],
                "ve": [2.7011560632672626e-10,7.436167948071671e-11,0.000004503549489433212,0,0,0],
                "st": {"gr":True,"as":0},
                "ti": 1678751444055,
                "m": "", 
                "ci": 0
            }
            try:
                response = requests.post(
                    "https://mps.geo-fs.com/update",
                    json = body,
                    cookies = {"PHPSESSID": self.sessionID}
                )
                print("Successfully connect to server.")
                response_body = json.loads(response.text)
                self.myID = response_body["myId"]


                body2 = {
                    "origin": "https://www.geo-fs.com",
                    "acid": self.accountID,
                    "sid": self.sessionID,
                    "id": self.myID,
                    "ac": "1",
                    "co": [9999999999999999,9999999999999999,999999999999999,9999999999999999,999999999999999,999999999999999],
                    "ve": [2.7011560632672626e-10,7.436167948071671e-11,0.000004503549489433212,0,0,0],
                    "st": {"gr":True,"as":0},
                    "ti": 1678751444055,
                    "m": "", 
                    "ci": self.lastMsgID
                }
                response = requests.post(
                    "https://mps.geo-fs.com/update",
                    json = body2,
                    cookies = {"PHPSESSID": self.sessionID}
                )
                response_body = json.loads(response.text)
                print(1)
                print(response_body)
                self.myID = response_body["myId"]
                self.lastMsgID = response_body["lastMsgId"]
                return
            except Exception as e:
                    print("Unable to connect to GeoFS. Check your connection and restart the application.")
                    print(f"Error message: {e}")
                    traceback.print_exc()
                    time.sleep(5)

    def sendMsg(self, msg):
        while True:
            body = {
                "origin": "https://www.geo-fs.com",
                "acid": self.accountID,
                "sid": self.sessionID,
                "id": self.myID,
                "ac": "1",
                "co": [9999999999999999,9999999999999999,999999999999999,9999999999999999,999999999999999,999999999999999],
                "ve": [2.7011560632672626e-10,7.436167948071671e-11,0.000004503549489433212,0,0,0],
                "st": {"gr":True,"as":0},
                "ti": None,
                "m": msg,
                "ci": self.lastMsgID
            }
            try:
                response = requests.post(
                    "https://mps.geo-fs.com/update",
                    json = body,
                    cookies = {"PHPSESSID": self.sessionID}
                )
                response_body = json.loads(response.text)
                self.myID = response_body["myId"]
                return
            except Exception as e:
                    print("Unable to connect to GeoFS. Check your connection and restart the application.")
                    print(f"Error message: {e}")
                    traceback.print_exc()
                    time.sleep(5)

    def getMessages(self):
        while True:
            body = {
                "origin": "https://www.geo-fs.com",
                "acid": self.accountID,
                "sid": self.sessionID,
                "id": self.myID,
                "ac": "1",
                "co": [9999999999999999,9999999999999999,999999999999999,9999999999999999,999999999999999,999999999999999],
                "ve": [2.7011560632672626e-10,7.436167948071671e-11,0.000004503549489433212,0,0,0],
                "st": {"gr":True,"as":0},
                "ti": None,
                "m": "",
                "ci": self.lastMsgID
            }
            try:
                response = requests.post(
                    "https://mps.geo-fs.com/update",
                    json = body,
                    cookies = {"PHPSESSID": self.sessionID}
                )
                response_body = json.loads(response.text)
                self.myID = response_body["myId"]
                self.lastMsgID = response_body["lastMsgId"]

                return response_body["chatMessages"]
            except Exception as e:
                print("Unable to connect to GeoFS. Check your connection and restart the application.")
                print(f"Error message: {e}")
                traceback.print_exc()
                time.sleep(5)