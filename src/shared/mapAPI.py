import json
import traceback
import time
from .http_client import safe_post


class BackendError(Exception):
    """Raised when the backend service returns an unexpected error."""
    pass


class Player:
    def __init__(self, userobj, aircraft_codes):
        try:
            #add grounded
            if "as" in userobj['st']:
                self.airspeed = userobj['st']['as']
            else:
                self.airspeed = 0
            self.userInfo = {'id':userobj['acid'],'callsign':userobj['cs']}
            self.coordinates = (userobj['co'][0] or 0,userobj['co'][1] or 0)
            self.altitude = round((userobj['co'][2] or 0) * 3.28084,2) # meters to feet
            self.verticalSpeed = round((userobj['co'][3] or 0) * 3.28084,2) # meters to feet
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
        except:
            print("Error in Player class")
            print(userobj)
            traceback.print_exc()
## MAIN CLASS ##

class MapAPI:
    """Client for interacting with the GeoFS map API."""
    def __init__(self):
        # Load aircraft code mappings
        with open('../../data/aircraftcodes.json', 'r') as f:
            self.aircraft_codes = json.load(f)

        self._responseList = []
        self._utilizeResponseList = True
        self.error = False

    def getUsers(self, foos):
        """
        Fetch list of online users from GeoFS map endpoint.

        Args:
            foos (bool | None):
                - True:   include only users whose callsign == 'Foo'
                - False:  exclude 'Foo' and empty callsigns
                - None:   include all users

        Returns:
            list[Player] | None: Parsed Player list, or None on failure.
        """
        payload = {'id': '', 'gid': None}
        response_body = safe_post(
            'https://mps.geo-fs.com/map',
            payload,
            timeout=(5, 15),
            max_json_retries=2
        )
        if response_body is None:
            self.error = True
            return None

        user_list = []
        for u in response_body.get('users', []):
            if not u or u.get('acid') is None:
                continue

            cs = u.get('cs', '')
            if foos is False and cs in ('Foo', ''):
                continue
            if foos is True and cs != 'Foo':
                continue

            user_list.append(Player(u, self.aircraft_codes))

        if self._utilizeResponseList:
            self._responseList.append(user_list)
        return user_list

    def returnResponseList(self, reset: bool):
        """
        Return the recorded response lists and optionally reset the internal buffer.

        Args:
            reset (bool): If True, clear the buffer after returning.

        Returns:
            list: The previously recorded lists of Player snapshots.
        """
        if reset:
            data = self._responseList
            self._responseList = []
            return data
        return self._responseList

    def disableResponseList(self):
        """Stop internally recording subsequent responses."""
        self._utilizeResponseList = False

    def enableResponseList(self):
        """Resume internally recording responses."""
        self._utilizeResponseList = True