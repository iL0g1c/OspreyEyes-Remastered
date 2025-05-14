# src/shared/multiplayerAPI.py

import json
import time
import traceback
from .http_client import safe_post


class MultiplayerAPI:
    def __init__(self, sessionID, accountID):
        self.sessionID = sessionID
        self.accountID = accountID
        self.myID = None
        self.lastMsgID = None

    def handshake(self):
        """Initialize connection; populate self.myID and self.lastMsgID."""
        while True:
            body = {
                "origin": "https://www.geo-fs.com",
                "acid": self.accountID,
                "sid": self.sessionID,
                "id": "",
                "ac": "1",
                "co": [9999999999999999]*6,
                "ve": [0.0]*6,
                "st": {"gr": True, "as": 0},
                "ti": int(time.time() * 1000),
                "m": "",
                "ci": 0
            }

            resp = safe_post(
                "https://mps.geo-fs.com/update",
                body,
                timeout=(5, 15),
                max_json_retries=2,
                cookies={"PHPSESSID": self.sessionID}
            )
            if not resp:
                print("Handshake failed, retrying in 5s…")
                traceback.print_exc()
                time.sleep(5)
                continue

            # first call gives us myID
            self.myID = resp.get("myId")

            # second call to pick up lastMsgId
            body["id"] = self.myID
            body["ci"] = self.lastMsgID
            resp2 = safe_post(
                "https://mps.geo-fs.com/update",
                body,
                timeout=(5, 15),
                max_json_retries=2,
                cookies={"PHPSESSID": self.sessionID}
            )
            if not resp2:
                print("Second handshake call failed, retrying in 5s…")
                traceback.print_exc()
                time.sleep(5)
                continue

            self.myID = resp2.get("myId")
            self.lastMsgID = resp2.get("lastMsgId")
            return

    def sendMsg(self, msg: str):
        """Post a chat message into Geo‑FS."""
        while True:
            body = {
                "origin": "https://www.geo-fs.com",
                "acid": self.accountID,
                "sid": self.sessionID,
                "id": self.myID,
                "ac": "1",
                "co": [9999999999999999]*6,
                "ve": [0.0]*6,
                "st": {"gr": True, "as": 0},
                "ti": None,
                "m": msg,
                "ci": self.lastMsgID
            }

            resp = safe_post(
                "https://mps.geo-fs.com/update",
                body,
                timeout=(5, 15),
                max_json_retries=2,
                cookies={"PHPSESSID": self.sessionID}
            )
            if resp:
                self.myID = resp.get("myId")
                return

            print("sendMsg failed, retrying in 5s…")
            traceback.print_exc()
            time.sleep(5)

    def getMessages(self) -> list[dict]:
        """Fetch latest chat messages and update self.lastMsgID."""
        while True:
            body = {
                "origin": "https://www.geo-fs.com",
                "acid": self.accountID,
                "sid": self.sessionID,
                "id": self.myID,
                "ac": "1",
                "co": [9999999999999999]*6,
                "ve": [0.0]*6,
                "st": {"gr": True, "as": 0},
                "ti": None,
                "m": "",
                "ci": self.lastMsgID
            }

            resp = safe_post(
                "https://mps.geo-fs.com/update",
                body,
                timeout=(5, 15),
                max_json_retries=2,
                cookies={"PHPSESSID": self.sessionID}
            )
            if resp:
                self.myID = resp.get("myId")
                self.lastMsgID = resp.get("lastMsgId")
                return resp.get("chatMessages", [])

            print("getMessages failed, retrying in 5s…")
            traceback.print_exc()
            time.sleep(5)