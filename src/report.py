import json
import math
import time
from collections import namedtuple

message_keys = ['Addr_type', 'Age', 'AgeLastAlt', 'Alt', 'AltIsGNSS', 'Bearing', 'BearingDist_valid', 'Distance',
                'DistanceEstimated', 'DistanceEstimatedLastTs', 'Emitter_category', 'ExtrapolatedPosition',
                'GnssDiffFromBaroAlt', 'Icao_addr', 'Last_GnssDiff', 'Last_GnssDiffAlt', 'Last_alt', 'Last_seen',
                'Last_source', 'Last_speed', 'Lat', 'Lng', 'NACp', 'NIC', 'OnGround', 'Position_valid',
                'PriorityStatus', 'Reg', 'SignalLevel', 'Speed', 'Speed_valid', 'Squawk', 'Tail', 'TargetType',
                'Timestamp', 'Track', 'Vvel']
Message = namedtuple("message", message_keys)


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

    def __init__(self, key, incoming_message: Message, report_list: "ReportList"):
        self.key = key
        self.identifier = ""
        self.last_updated = time.time()
        self.age = incoming_message.Age
        self.altitude = incoming_message.Alt
        self.altitude_change = self.LEVEL
        self.vertical_velocity = 0
        self.message = incoming_message
        self.report_list = report_list
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
        return calculate_crossing_time(self.report_list.situation_dictionary["OwnAltitude"],
                                       self.report_list.situation_dictionary["OwnVerticalVelocity"],
                                       self.altitude, self.vertical_velocity)

    def get_distance_score(self) -> float:
        minutes_until_altitude_crossing = self.get_altitude_crossing_time()
        score = math.fabs(minutes_until_altitude_crossing) * self.get_distance() * math.fabs(
            self.report_list.situation_dictionary["OwnAltitude"] - self.altitude) / 100000
        return score

    def get_distance(self) -> float:
        if self.is_good_distance():
            return distance_to_nm(self.message.Distance)
        return distance_to_nm(self.message.DistanceEstimated)

    def is_good_distance(self) -> bool:
        return self.message.BearingDist_valid and self.message.Position_valid and self.report_list.status_dictionary[
            "GPS_connected"]

    def get_age(self) -> float:
        return self.message.Age + time.time() - self.last_updated

    def __str__(self):
        return "{}: {}s".format(self.identifier, self.get_age())


class ReportList:
    def __init__(self, status_dictionary, situation_dictionary):
        self.reports = {}
        self.ship_count = 0
        self.key_map = {}
        self.status_dictionary = status_dictionary
        self.situation_dictionary = situation_dictionary
        self.include_valid_positions = True

    def toggle_include_valid_positions(self, value=None):
        if value is not None:
            self.include_valid_positions = value
        else:
            self.include_valid_positions = not self.include_valid_positions
        if self.include_valid_positions:
            print("Including valid positions")
        else:
            print("Not including valid positions")

    def get_include_valid_positions(self):
        return self.include_valid_positions

    def get_selected_reports(self):
        if not self.get_include_valid_positions():
            return [item for item in self.reports.values() if not item.message.Position_valid]
        else:
            return self.reports.values()

    def get_list_sorted_score(self):
        return sorted(self.get_selected_reports(), key=lambda k: k.get_distance_score())

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
            latest_report = LatestReport(k, message, self)
            self.reports[k] = latest_report
        # else:
        # print("Found existing report for key: {}".format(k))
        latest_report.update_report(message)
        return latest_report


def read_response(response):
    data = json.loads(response)
    return Message(*[data[key] for key in sorted(data.keys())])


def get_identifiers(message: Message):
    return message.Addr_type, message.Icao_addr, message.Squawk, message.Tail


def get_identifier(message: Message):
    if len(message.Tail) > 0:
        return message.Tail
    if message.Squawk > 0:
        return message.Squawk
    if message.Icao_addr > 0:
        return "{:X}".format(message.Icao_addr)
    return ""
