import urequests
from m5stack import *
from m5ui import *
import wifiCfg
import uwebsockets.client
import gc

from display_manager import *
from report import *

STRATUX_ADDRESS = "192.168.10.1"
STRATUX_SSID = "stratux"

key_map = {}
status_dictionary = {}
situation_dictionary = {}


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


reports_list = ReportList(status_dictionary, situation_dictionary)
display_manager = DisplayManager(reports_list, status_dictionary, situation_dictionary)
display_manager.select_display(display_manager.AIRCRAFT_LIST)

# button_c_pressed = False
# button_c_double_press = False
# def button_c_press_handler():
#     global button_c_pressed
#     button_c_pressed = True
#
# def button_c_double_press_handler():
#     global button_c_double_press
#     button_c_double_press = True
#
# def button_c_released_handler():
#     global button_c_pressed, button_c_double_press
#     if button_c_double_press:
#         reports_list.toggle_include_valid_positions()
#     else:
#         display_manager.button_c_was_pressed()
#     button_c_double_press = False
#     button_c_pressed = False


btnA.wasPressed(display_manager.button_a_was_pressed)
btnB.wasPressed(display_manager.button_b_was_pressed)
btnC.wasPressed(display_manager.button_c_was_pressed)
# btnC.wasReleased(button_c_released_handler)
# btnC.wasDoublePress(button_c_double_press_handler)

# alerting = False
# alert_start = 0
#
#
# @timerSch.event('alarm_event')
# def alarm():
#     global display_manager, alerting, alert_start
#     if alert_start == 0:
#         alert_start = time.time()
#     if time.time() - alert_start > 10:
#         display_manager.cancel_alarm()
#         alert_start = 0
#         alerting = False
#         return
#     if alerting:
#         display_manager.alerting = True
#         alerting = False
#     else:
#         display_manager.alerting = False
#         alerting = True


gps_fix = False
while not wifiCfg.wlan_sta.isconnected():
    wifiCfg.doConnect(STRATUX_SSID, '')
display_manager.update_connection_status('Stratux connected')
websocket = uwebsockets.client.connect("ws://{}/traffic".format(STRATUX_ADDRESS))
websocket.settimeout(5)
start_time = time.time()
last_time = 0

while True:
    try:
        resp = websocket.recv()
        message = read_response(resp)
        # print(message)
        report = reports_list.store_report(message)
        # print(report)
    except Exception as e:
        print(e)
        try:
            websocket.close()
        except:
            pass
        websocket = uwebsockets.client.connect("ws://{}/traffic".format(STRATUX_ADDRESS))
        websocket.settimeout(15)

    now = time.time()
    if now - last_time > 5:
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
        print("Free memory: {}".format(gc.mem_free()))
