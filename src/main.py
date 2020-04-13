import urequests
from m5stack import *
from m5ui import *
import wifiCfg
import uwebsockets.client
import gc
import utime as time

from display_manager import *
from report import *

STRATUX_ADDRESS = "192.168.10.1"
STRATUX_SSID = "stratux"

key_map = {}
status_dictionary = {}
situation_dictionary = {}

SCREEN_UPDATE_TIME = const(4)
WEBSOCKET_ERROR_TIMEOUT = const(30)
SOCKET_TIMEOUT = const(0.1)

def _get(url: str):
    r = urequests.get(url)
    try:
        return r.json()
    except:
        return {}


def get_situation():
    global situation_dictionary
    data = _get("http://{}/getSituation".format(STRATUX_ADDRESS))
    situation_dictionary.update(data)


def get_my_altitude():
    global situation_dictionary
    previous_altitude = situation_dictionary.get("GPSAltitudeMSL")
    previous_vertical_velocity = situation_dictionary.get("GPSVerticalSpeed")
    get_situation()
    situation_dictionary["OwnAltitude"] = situation_dictionary.get("GPSAltitudeMSL", previous_altitude)
    situation_dictionary["OwnVerticalVelocity"] = situation_dictionary.get("GPSVerticalSpeed",
                                                                           previous_vertical_velocity)


def get_status(display_manager):
    global status_dictionary
    status = _get("http://{}/getStatus".format(STRATUX_ADDRESS))
    display_manager.updated_gps_status(
        "{} {}/{} {}m".format("GPS" if status["GPS_connected"] else "NO GPS", status["GPS_satellites_locked"],
                              status["GPS_satellites_tracked"], status["GPS_position_accuracy"]))
    status_dictionary.update(status)


def create_websocket():
    websocket = uwebsockets.client.connect("ws://{}/traffic".format(STRATUX_ADDRESS))
    websocket.settimeout(SOCKET_TIMEOUT)
    return websocket


reports_list = ReportList(status_dictionary, situation_dictionary)
display_manager = DisplayManager(reports_list, status_dictionary, situation_dictionary)

btnA.wasPressed(display_manager.button_a_was_pressed)
btnB.wasPressed(display_manager.button_b_was_pressed)
btnC.wasPressed(display_manager.button_c_was_pressed)


gps_fix = False
while not wifiCfg.wlan_sta.isconnected():
    wifiCfg.doConnect(STRATUX_SSID, '')
display_manager.update_connection_status('Stratux connected')
websocket = create_websocket()
display_manager.select_display(display_manager.AIRCRAFT_LIST)

start_time = time.time()
last_time = 0
last_report = 0
while True:
    try:
        resp = websocket.recv()
        last_report = time.time()
        message = read_response(resp)
        # print(message)
        try:
            report = reports_list.store_report(message)
            print(report)
        except Exception as e:
            print(e)
    except Exception as e:
        pass
    if time.time() - last_report > WEBSOCKET_ERROR_TIMEOUT:
        try:
            websocket.close()
        except:
            pass
        websocket = create_websocket()
        last_report = time.time()

    now = time.time()
    if now - last_time > SCREEN_UPDATE_TIME:
        last_time = now
        try:
            get_status(display_manager)
        except Exception as e:
            print("Failed getting status: {}".format(e))
        try:
            get_my_altitude()
        except Exception as e:
            print("Failed getting situation: {}".format(e))
        reports_list.flush_old_reports()
        display_manager.update_display()
        print("Free memory: {} B".format(gc.mem_free()))
