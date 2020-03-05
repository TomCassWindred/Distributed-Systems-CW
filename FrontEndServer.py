import Pyro4
import Pyro4.errors
import sys
import requests
import json

UPDATE_ATTEMPTS = 5  # How many times to attempt to run a function and updateInterfaces before giving up


# Test all interfaces to see which one is working
# use name server object lookup uri shortcut
def updateInterfaces(brokenProxy=None):
    global interfacenames, workinginterfaces, currInterface
    if brokenProxy and len(workinginterfaces) > 1:
        workinginterfaces.remove(brokenProxy)
        currInterface = workinginterfaces[0]
        return True

    workinginterfaces = []
    for name in interfacenames:
        try:
            interface = Pyro4.Proxy(name)
            interface._pyroBind()
            interface.ping()
            if not currInterface:
                currInterface = interface
            workinginterfaces.append(interface)
        except Pyro4.errors.CommunicationError as err:
            print(f"Interface: {name} is not working, error: {err}")
        except Pyro4.errors.NamingError:
            print(f"Interface: {name} is not recognised by the nameserver, likely is not running")
        except AttributeError:
            print(f"Ping was not recognised as a valid method, interface is incorrect")

    if not workinginterfaces:
        print("No interfaces are working! Closing frontend...")
        sys.exit()
    else:
        print(f"The following interfaces are working: {workinginterfaces}")
        if currInterface == brokenProxy:
            print("It would appear that the proxy this function was called on was working, trying again")
            print("This should not happen, and if it does, we are all pretty screwed")


def distanceAPIcall(address1, address2):
    print(f"Getting Distance between \"{address1}\" and \"{address2}\"")
    url = f"http://dev.virtualearth.net/REST/V1/Routes/Driving?wp.0={address1}%2Cwa&wp.1={address2}%2Cwa&avoid=minimizeTolls&distanceUnit=mi&key=L7CjHmVZPbKmelVWL8pu~DWGkwVtxhcPqfBd6Evk7Aw~AqQlqFTm-6iQm6KwJs4dpqW5LJWCO-I8Vn2rk0lFv9FNJ5D21MYDgXeRr82fxVw4"

    response = json.loads(requests.request("GET", url).text)
    if "errorDetails" in response:
        if response["errorDetails"][0] == 'The internal route service returned a timeout error code in the response':
            raise Exception("Distance API Timed Out")
        if response["errorDetails"][0] == "No route was found for the waypoints provided.":
            raise Exception("Failed to find route")
        raise Exception(f"Distance API Exception: {response['errorDetails'][0]}")
    else:
        resource = response["resourceSets"][0]["resources"][0]
        return resource['travelDistance'], resource['travelDurationTraffic']


# print(getdistance("12 Percy Square, Durham, DH1 3PZ", "86 Fuckyou Fuckenu, Fuckslyvania, Fuck, 123 123"))
def safeRun(func, args):
    for i in range(UPDATE_ATTEMPTS):
        try:
            return func(*args)
        except ConnectionError:
            updateInterfaces(currInterface)



@Pyro4.expose
class ClientInterface:
    def getrestruants(self, address, postcode):
        return safeRun(currInterface.getrestruants, (address, postcode))


    def getmenuitems(self, restruant):
        return safeRun(currInterface.getmenuitems, (restruant, ))

    def getdistance(self, address, postcode, restruant):
        try:
            restruantaddr = safeRun(currInterface.getaddress, (restruant, ))
            return distanceAPIcall(f"{address}, {postcode}", restruantaddr)
        except Exception as err:
            if err == "Distance API Timed Out" or err == "Failed to find route":
                return False, err
            else:
                print(err)
                return False, "Unknown Error"

    def makeorder(self, name, fulladdress, basket):
        try:
            safeRun(currInterface.makeorder, (name, fulladdress, basket))
            return True
        except Exception:
            return False


interfacenames = ["PYRONAME:back.interface.alpha",
                  "PYRONAME:back.interface.beta",
                  "PYRONAME:back.interface.gamma"]
workinginterfaces = []
currInterface = None
updateInterfaces()

daemon = Pyro4.Daemon()  # make a Pyro daemon
ns = Pyro4.locateNS()  # find the name server
uri = daemon.register(ClientInterface)  # register the greeting maker as a Pyro object
ns.register("front.interface", uri)  # register the object with a name in the name server

print("Ready.")
daemon.requestLoop()  # start the event loop of the server to wait for calls
