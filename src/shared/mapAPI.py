import requests
import json
import traceback
import time

## EXCEPTIONS ##
class BackendError(Exception):
    pass

## USER CLASSES ##

class Player:
    def __init__ (self,userobj, aircrafCodes):
        #add grounded
        self.airspeed = userobj['st']['as']
        self.userInfo = {'id':userobj['acid'],'callsign':userobj['cs']}
        self.coordinates = (userobj['co'][0],userobj['co'][1])
        self.altitude = round(userobj['co'][2]*3.28084,2) # meters to feet
        self.verticalSpeed = round(userobj['co'][3]*3.28084,2) # meters to feet
        try:
            self.aircraft = {
                'type':aircrafCodes[str(userobj['ac'])]["name"],
                'id':userobj['ac']
            }
        except KeyError:
            self.aircraft = {
                'type':"Unknown",
                'id':userobj['ac']
            }
## MAIN CLASS ##
class MapAPI:
    def __init__(self):
        with open("../../data/aircraftcodes.json", "r") as reader:
            self.aircrafCodes = json.load(reader)
        self._responseList = []
        self._utilizeResponseList = True
        self.error = False
    def getUsers(self,foos, max_retries=10, backoff_factor=2):
        attempt = 0
        while attempt <= max_retries:
            self.error = False
            try:
                response = requests.post(
                    "https://mps.geo-fs.com/map",
                    json = {
                        "id":"",
                        "gid": None
                    }
                )
                response.raise_for_status()
                response_body = response.json()

                userList = []
                for user in response_body['users']:
                    if user == None:
                        continue
                    elif user['acid'] == None:
                        continue
                    elif foos == False:
                        if user['cs'] == "Foo" or user['cs'] == '':
                            pass
                        else:
                            userList.append(Player(user, self.aircrafCodes))
                    elif foos == True:
                        if user['cs'] != "Foo":
                            pass
                        else:
                            userList.append(Player(user, self.aircrafCodes))
                    elif foos == None:
                        userList.append(Player(user, self.aircrafCodes))
                    else:
                        raise AttributeError('"Foos" attribute must be boolean or NoneType.')
                    
                if self._utilizeResponseList:
                    self._responseList.append(userList)
                return userList
            except (requests.RequestException, json.JSONDecodeError) as e:
                self.error = True
                print(f"Error on attempt {attempt + 1}: Unable to connect to GeoFS. Error: {e}")
                traceback.print_exc()
                attempt += 1
                if attempt <= max_retries:
                    wait_time = backoff_factor ** attempt
                    print(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    print("Max retries reached. Please check your connection and restart the application.")
                    return None

    def returnResponseList(self,reset:bool):
        if reset == True:
            before = self._responseList
            self._responseList = []
            return before
        return self._responseList
    def disableResponseList(self):
        self._utilizeResponseList = False
    def enableResponseList(self):
        self._utilizeResponseList = True


'''
st gr -- grounded
st as -- airspeed
ac -- aircraft number [refr aircraftcodes.json]
acid -- user id
cs -- callsign
co 0 latitude
co 1 longitude
co 2 altitude in meters
co 3 vertical speed in meters
'''