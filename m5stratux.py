import json
import math
from collections import namedtuple
import time
import urequests
from m5stack import *
from m5ui import *
import wifiCfg
import uwebsockets.client
import gc

STRATUX_ADDRESS = "192.168.10.1"
# from ucollections import namedtuple

# < {"Icao_addr":4692788,"Reg":"","Tail":"","Emitter_category":0,"OnGround":false,"Addr_type":0,"TargetType":0,"SignalLevel":-29.442395353122652,"Squawk":0,"Position_valid":false,"Lat":0,"Lng":0,"Alt":0,"GnssDiffFromBaroAlt":0,"AltIsGNSS":false,"NIC":0,"NACp":0,"Track":0,"Speed":0,"Speed_valid":false,"Vvel":0,"Timestamp":"2020-04-08T20:24:02.455Z","PriorityStatus":0,"Age":54.56,"AgeLastAlt":54.56,"Last_seen":"0001-01-01T07:01:09.4Z","Last_alt":"0001-01-01T07:01:09.4Z","Last_GnssDiff":"0001-01-01T00:00:00Z","Last_GnssDiffAlt":0,"Last_speed":"0001-01-01T00:00:00Z","Last_source":1,"ExtrapolatedPosition":false,"BearingDist_valid":true,"Bearing":192.9080069776909,"Distance":6784177.245384362,"DistanceEstimated":26583.99790612144,"DistanceEstimatedLastTs":"2020-04-08T20:24:02.455Z"}
message_keys = ['Addr_type', 'Age', 'AgeLastAlt', 'Alt', 'AltIsGNSS', 'Bearing', 'BearingDist_valid', 'Distance',
                'DistanceEstimated', 'DistanceEstimatedLastTs', 'Emitter_category', 'ExtrapolatedPosition',
                'GnssDiffFromBaroAlt', 'Icao_addr', 'Last_GnssDiff', 'Last_GnssDiffAlt', 'Last_alt', 'Last_seen',
                'Last_source', 'Last_speed', 'Lat', 'Lng', 'NACp', 'NIC', 'OnGround', 'Position_valid',
                'PriorityStatus', 'Reg', 'SignalLevel', 'Speed', 'Speed_valid', 'Squawk', 'Tail', 'TargetType',
                'Timestamp', 'Track', 'Vvel']
Message = namedtuple("message", (message_keys))

global_own_altitude = 0
global_own_vertical_velocity = 0


def distance_to_nm(distance: float) -> float:
    return distance / (1000 * 1.852)


def calculate_crossing_time(our_altitude: float, our_vertical: float, their_altitude: float,
                            their_vertical: float) -> float:
    """
    Negative return value means they crossed in the past so will never cross in the future

    :param our_altitude: ft
    :param our_vertical: fpm
    :param their_altitude: ft
    :param their_vertical: fpm
    :return: Minutes until crossing
    """
    if their_vertical - our_vertical == 0:
        return 99
    return min((our_altitude - their_altitude) / (their_vertical - our_vertical), 99)


class LatestReport:
    DESCENDING = 0
    CLIMBING = 1
    LEVEL = 2

    def __init__(self, key, incoming_message: Message):
        self.key = key
        self.identifier = ""
        self.last_updated = time.time()
        self.age = incoming_message.Age
        self.altitude = incoming_message.Alt
        self.altitude_change = self.LEVEL
        self.vertical_velocity = 0
        self.update_report(incoming_message)

    def update_report(self, incoming_message: Message):
        self.identifier = get_identifier(incoming_message)
        self.age = incoming_message.Age
        self.last_updated = time.time()
        if incoming_message.Alt > self.altitude:
            self.altitude_change = self.CLIMBING
        elif incoming_message.Alt < self.altitude:
            self.altitude_change = self.DESCENDING
        else:
            self.altitude_change = self.LEVEL
        if incoming_message.Vvel == 0:
            self.vertical_velocity = incoming_message.Alt - self.altitude
        else:
            self.vertical_velocity = incoming_message.Vvel
        self.altitude = incoming_message.Alt
        self.message = incoming_message

    def get_altitude_crossing_time(self) -> float:
        global global_own_altitude, global_own_vertical_velocity
        # print("{}: ({}-{})/({}-{})".format(self.identifier, global_own_altitude, self.altitude, self.vertical_velocity, global_own_vertical_velocity))
        return calculate_crossing_time(global_own_altitude, global_own_vertical_velocity,
                                       self.altitude, self.vertical_velocity)

    def get_distance_score(self) -> float:
        minutes_until_altitude_crossing = self.get_altitude_crossing_time()
        score = math.fabs(minutes_until_altitude_crossing) * self.get_distance() * math.fabs(
            global_own_altitude - self.altitude)/100000
        return score

    def get_distance(self) -> float:
        if self.is_good_distance():
            return distance_to_nm(self.message.Distance)
        return distance_to_nm(self.message.DistanceEstimated)

    def is_good_distance(self) -> bool:
        global gps_fix
        return self.message.BearingDist_valid and self.message.Position_valid and gps_fix

    def get_age(self) -> float:
        return self.message.Age + time.time() - self.last_updated

    def __str__(self):
        return "{}: {}s".format(self.identifier, self.get_age())


class ReportList:
    def __init__(self):
        self.reports = {}
        self.ship_count = 0
        self.key_map = {}

    def get_list_sorted_score(self):
        return sorted(self.reports.values(), key=lambda k: k.get_distance_score())

    def flush_old_reports(self):
        for key in self.reports.keys():
            if self.reports[key].get_age() > 60:
                del self.reports[key]

    def map_to_key(self, message: Message):
        key = self.key_map.get(message.Tail)
        if not key:
            key = self.key_map.get(message.Squawk)
            if not key:
                key = self.key_map.get("{:X}".format(message.Icao_addr))
                if not key:
                    # Create new key
                    self.ship_count += 1
                    key = self.ship_count
                    self.key_map[get_identifier(message)] = key
        return key

    def store_report(self, message: Message) -> LatestReport:
        k = self.map_to_key(message)
        latest_report = self.reports.get(k)
        if not latest_report:
            # print("Did not find report for key: {}".format(k))
            latest_report = LatestReport(k, message)
            self.reports[k] = latest_report
        # else:
        # print("Found existing report for key: {}".format(k))
        latest_report.update_report(message)
        return latest_report


def read_response(response):
    data = json.loads(response)
    return Message(*[data[key] for key in sorted(data.keys())])


def get_identifiers(message: Message):
    return (message.Addr_type, message.Icao_addr, message.Squawk, message.Tail)


def get_identifier(message: Message):
    if len(message.Tail) > 0:
        return message.Tail
    if message.Squawk > 0:
        return message.Squawk
    if message.Icao_addr > 0:
        return "{:X}".format(message.Icao_addr)
    return ""


class DisplayManager:
    AIRCRAFT_LIST = 0
    AIRCRAFT_DETAILS = 1
    ALERT_PAGE = 2
    DISPLAY_TYPES = (AIRCRAFT_LIST, AIRCRAFT_DETAILS)  # , ALERT_PAGE)

    def __init__(self, report_list: ReportList):
        lcd.clear()
        self.connection_status = M5TextBox(0, 0, "Connecting to Stratux", lcd.FONT_Default, 0xFFFFFF, rotate=0)
        self.gps_status = M5TextBox(150, 0, "Connecting to GPS", lcd.FONT_Default, 0xFFFFFF, rotate=0)
        self.selected_display = self.AIRCRAFT_LIST
        self.report_list = report_list
        self.display_list = {}
        self.active_display = None
        self.display_box = M5TextBox(130, 225, "NEXT", lcd.FONT_Default, lcd.GREEN, rotate=0)

    def update_connection_status(self, text):
        self.connection_status.setText(text)

    def updated_gps_status(self, text):
        self.gps_status.setText(text)

    def __create_display(self, display: int):
        if display == self.AIRCRAFT_LIST:
            return ListDisplay(self.report_list)
        if display == self.AIRCRAFT_DETAILS:
            return DetailDisplay(self.report_list)

    def select_display(self, display_type: int):
        if self.active_display:
            self.active_display.hide()
        if display_type not in self.display_list:
            self.display_list[display_type] = self.__create_display(display_type)
        self.selected_display = display_type
        self.active_display = self.display_list[display_type]
        self.active_display.show()

    def update_display(self):
        self.active_display.update_display()

    def button_a_was_pressed(self):
        """
        Display specific button
        """
        self.active_display.button_a_was_pressed()

    def button_b_was_pressed(self):
        """
        Cycle next display
        """
        current_index = self.DISPLAY_TYPES.index(self.selected_display)
        current_index += 1
        if current_index == len(self.DISPLAY_TYPES):
            current_index = 0
        self.select_display(self.DISPLAY_TYPES[current_index])

    def button_c_was_pressed(self):
        self.active_display.button_c_was_pressed()


class Display:
    def show(self):
        pass

    def hide(self):
        pass

    def update_display(self):
        pass

    def button_a_was_pressed(self):
        pass

    # def button_b_was_pressed(self):
    #     pass
    # 
    # def button_c_was_pressed(self):
    #     pass


class DetailDisplay(Display):
    ROW_SPACING = 25
    ROW_OFFSET = 30

    def __init__(self, reports: ReportList):
        self.reports_list = reports
        self.reports = []
        self.current_index = 0
        self.report = None
        self.visible = False
        self.font = lcd.FONT_DejaVu24
        self.background_colour = 0xFFFFFF
        self.identifier = M5TextBox(140, self.ROW_SPACING + self.ROW_OFFSET, "", self.font,
                                    lcd.MAGENTA,
                                    rotate=0)
        self.distance = M5TextBox(10, 2 * self.ROW_SPACING + self.ROW_OFFSET, "", self.font,
                                  self.background_colour,
                                  rotate=0)
        self.altitude = M5TextBox(200, 2 * self.ROW_SPACING + self.ROW_OFFSET, "", self.font,
                                  self.background_colour,
                                  rotate=0)
        self.crossing_time = M5TextBox(0, 3 * self.ROW_SPACING + self.ROW_OFFSET, "",
                                       self.font,
                                       self.background_colour,
                                       rotate=0)
        self.score = M5TextBox(150, 3 * self.ROW_SPACING + self.ROW_OFFSET, "",
                               self.font,
                               self.background_colour,
                               rotate=0)
        self.age = M5TextBox(250, 3 * self.ROW_SPACING + self.ROW_OFFSET, "", self.font,
                             self.background_colour,
                             rotate=0)
        self.altitude_difference = M5TextBox(0, 4 * self.ROW_SPACING + self.ROW_OFFSET, "",
                                             self.font,
                                             self.background_colour,
                                             rotate=0)

    def hide(self):
        self.visible = False
        self.identifier.hide()
        self.distance.hide()
        self.altitude.hide()
        self.crossing_time.hide()
        self.score.hide()
        self.age.hide()
        self.altitude_difference.hide()

    def show(self):
        self.visible = True
        self.identifier.show()
        self.distance.show()
        self.altitude.show()
        self.crossing_time.show()
        self.score.show()
        self.age.show()
        self.altitude_difference.show()
        self.display_index(0)

    def update_display(self):
        global global_own_altitude
        new_report_list = self.reports_list.get_list_sorted_score()
        self.reports = new_report_list
        if len(new_report_list) == 0:
            return
        self.current_index = min(len(new_report_list), self.current_index)
        report = new_report_list[self.current_index]
        self.identifier.setText("{}".format(report.identifier))
        if report.is_good_distance():
            self.distance.setText("{:>.0f}nm".format(report.get_distance()))
        else:
            self.distance.setText("({:>.0f})nm".format(report.get_distance()))
        self.altitude.setText("{: >5}ft".format(report.altitude))
        self.crossing_time.setText("c{:.1f}m".format(report.get_altitude_crossing_time()))
        self.score.setText("s{:.1f}".format(report.get_distance_score()))
        self.age.setText("{:>3.0f}s".format(report.get_age()))
        self.altitude_difference.setText("{:.0f}ft".format(report.altitude - global_own_altitude))

    def display_index(self, index: int):
        self.current_index = index
        self.update_display()

    def next_index(self):
        self.current_index += 1
        if self.current_index >= len(self.reports):
            self.current_index = 0
        self.update_display()

    def button_a_was_pressed(self):
        self.next_index()


class ListDisplay(Display):
    ROW_SPACING = 50
    ROW_OFFSET = 30
    NUMBER_OF_ROWS = 4

    # 320 x 240
    def __init__(self, reports: ReportList):
        self.reports_list = reports
        self.reports = []
        self.number_of_rows = 4
        self.font = lcd.FONT_DejaVu24
        self.background_colour = 0xFFFFFF
        self.visible = False
        self.rows = []
        self.list_offset = 0
        self.number_of_pages = 0
        self.current_page = 0
        self.previous_report_list = []
        for index in range(self.number_of_rows):
            self.rows.append((
                M5TextBox(0, index * self.ROW_SPACING + self.ROW_OFFSET, "", self.font, self.background_colour,
                          rotate=0),
                M5TextBox(100, index * self.ROW_SPACING + self.ROW_OFFSET, "", self.font, self.background_colour,
                          rotate=0),
                M5TextBox(200, index * self.ROW_SPACING + self.ROW_OFFSET, "", self.font, self.background_colour,
                          rotate=0),
                M5TextBox(0, index * self.ROW_SPACING + self.ROW_OFFSET + int(self.ROW_SPACING / 2), "", self.font,
                          self.background_colour,
                          rotate=0),
                M5TextBox(150, index * self.ROW_SPACING + self.ROW_OFFSET + int(self.ROW_SPACING / 2), "", self.font,
                          self.background_colour,
                          rotate=0),
                M5TextBox(250, index * self.ROW_SPACING + self.ROW_OFFSET + int(self.ROW_SPACING / 2), "", self.font,
                          self.background_colour,
                          rotate=0)
            ))
        self.page_box = M5TextBox(50, 225, "1/0", lcd.FONT_Default, lcd.GREEN, rotate=0)
        self.hide()

    def hide(self):
        self.visible = False
        self.page_box.hide()
        for row in self.rows:
            for box in row:
                box.hide()

    def show(self):
        self.visible = True
        self.page_box.show()
        for row in self.rows:
            for box in row:
                box.show()

    def display_report(self, report: LatestReport, index: int):
        print("Setting report: {}".format(report))
        self.rows[index][0].setText("{}".format(report.identifier))
        if report.is_good_distance():
            self.rows[index][1].setText("{:>.0f}nm".format(report.get_distance()))
        else:
            self.rows[index][1].setText("({:>.0f})nm".format(report.get_distance()))
        self.rows[index][2].setText("{: >5}ft".format(report.altitude))
        self.rows[index][3].setText("c{:.1f}m".format(report.get_altitude_crossing_time()))
        self.rows[index][4].setText("s{:.1f}".format(report.get_distance_score()))
        self.rows[index][5].setText("{:>3.0f}s".format(report.get_age()))

    def clear_row(self, index: int):
        for box in range(6):
            self.rows[index][box].setText("")

    def update_display(self):
        new_report_list = self.reports_list.get_list_sorted_score()
        self.page_box.setText(
            "{}/{}".format(self.current_page + 1, int(math.ceil(len(new_report_list) / self.number_of_rows))))
        first_report_index = max(
            min(self.current_page * self.number_of_rows, len(new_report_list) - self.number_of_rows), 0)
        last_report_index = min(first_report_index + self.number_of_rows, len(new_report_list))
        row_index = -1
        for index in range(first_report_index, last_report_index):
            print(index)
            row_index = index - first_report_index
            self.display_report(new_report_list[index], row_index)
        for index in range(row_index + 1, self.number_of_rows):
            self.clear_row(index)
        self.reports = new_report_list

    def next_page(self):
        self.current_page += 1
        if self.current_page >= self.number_of_pages:
            self.current_page = 0
        self.update_display()

    def previous_page(self):
        self.current_page -= 1
        if self.current_page < 0:
            self.current_page = self.number_of_pages - 1
        self.update_display()

    def button_a_was_pressed(self):
        self.next_page()


key_map = {}


def _get(url: str):
    r = urequests.get(url)
    try:
        return r.json()
    except:
        return {}


def get_situation():
    return _get("http://{}/getSituation".format(STRATUX_ADDRESS))


def get_my_altitude():
    situation = get_situation()
    my_barometer = situation.get("BaroPressureAltitude")
    my_barometer_vertical_speed = situation.get("BaroVerticalSpeed")
    my_gps = situation.get("GPSAltitudeMSL")
    my_gps_vertical_speed = situation.get("GPSVerticalSpeed")
    return (my_barometer, my_barometer_vertical_speed, my_gps, my_gps_vertical_speed)


def get_status(display_manager):
    global gps_fix
    status = _get("http://{}/getStatus".format(STRATUX_ADDRESS))
    display_manager.updated_gps_status(
        "{} {}/{} {}m".format("GPS" if status["GPS_connected"] else "NO GPS", status["GPS_satellites_locked"],
                              status["GPS_satellites_tracked"], status["GPS_position_accuracy"]))
    gps_fix = status["GPS_connected"]


reports_list = ReportList()
display_manager = DisplayManager(reports_list)
display_manager.select_display(display_manager.AIRCRAFT_LIST)
btnA.wasPressed(display_manager.button_a_was_pressed)
btnB.wasPressed(display_manager.button_b_was_pressed)
btnC.wasPressed(display_manager.button_c_was_pressed)

# title = M5Title(title="Stratux")
gps_fix = False
while not wifiCfg.wlan_sta.isconnected():
    wifiCfg.doConnect('stratux', '')
display_manager.update_connection_status('wifi connected')
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
        websocket.settimeout(5)

    now = time.time()
    if now - last_time > 5:
        last_time = now
        try:
            get_status(display_manager)
        except Exception as e:
            print("Failed getting status: {}".format(e))
        pa, pv = global_own_altitude, global_own_vertical_velocity
        try:
            _, _, global_own_altitude, global_own_vertical_velocity = get_my_altitude()
            print("Try own alt: {}".format(global_own_altitude))
            print("Try own vertical {}".format(global_own_vertical_velocity))
        except Exception as e:
            print("Failed getting situation: {}".format(e))
        if global_own_altitude is None or global_own_vertical_velocity is None:
            global_own_altitude, global_own_vertical_velocity = pa, pv
        print("Own alt: {}".format(global_own_altitude))
        print("Own vertical {}".format(global_own_vertical_velocity))
        reports_list.flush_old_reports()
        display_manager.update_display()
        print(gc.mem_free())