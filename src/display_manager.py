import json
import utime as time

from m5stack import *
from m5ui import *

import math

from clip_line import SCREEN_HEIGHT, SCREEN_WIDTH, clip_line, HEADER_OFFSET, FOOTER_OFFSET, extend_line


class DisplayManager:
    AIRCRAFT_LIST = 0
    AIRCRAFT_DETAILS = 1
    NEAREST_PAGE = 2
    ALERT_PAGE = 3
    MESSAGE_PAGE = 4
    SETTINGS_PAGE = 5
    ALTITUDE_PROFILE_PAGE = 6
    DISPLAY_TYPES = (AIRCRAFT_LIST, ALTITUDE_PROFILE_PAGE, NEAREST_PAGE, SETTINGS_PAGE)

    def __init__(self, report_list: "ReportList", status_dictionary, situation_dictionary):
        self.status_dictionary = status_dictionary
        self.situation_dictionary = situation_dictionary
        lcd.clear()
        self.connection_status = M5TextBox(0, 0, "Connecting to Stratux", lcd.FONT_Default, 0xFFFFFF, rotate=0)
        self.gps_status = M5TextBox(150, 0, "Connecting to GPS", lcd.FONT_Default, 0xFFFFFF, rotate=0)
        self.selected_display = -1
        self.previous_display = self.selected_display
        self.report_list = report_list
        self.trigger_update_display = False
        self.trigger_select_display = -1
        self.display_list = {}
        self.active_display = None
        self.display_box = M5TextBox(130, 225, "SCREEN", lcd.FONT_Default, lcd.GREEN, rotate=0)
        self.alert_time = -1
        self.__create_displays()

    def update_connection_status(self, text):
        self.connection_status.setText(text)

    def updated_gps_status(self, text):
        self.gps_status.setText(text)

    def __create_displays(self):
        self.display_list[self.AIRCRAFT_LIST] = ListDisplay(self.report_list, self)
        # self.display_list[self.AIRCRAFT_DETAILS] = DetailDisplay(self.report_list, self)
        self.display_list[self.NEAREST_PAGE] = NearestDisplay(self.report_list, self)
        self.display_list[self.ALERT_PAGE] = AlertDisplay()
        # self.display_list[self.MESSAGE_PAGE] = MessageDisplay(self)
        self.display_list[self.SETTINGS_PAGE] = SettingsPage(self.report_list, self)
        self.display_list[self.ALTITUDE_PROFILE_PAGE] = AltitudeProfilePage(self.report_list, self)

    def select_display(self, display_type: int):
        self.trigger_select_display = display_type
        self.trigger_update_display = True

    def actually_change_display(self):
        display_type = self.trigger_select_display
        self.trigger_select_display = -1
        if self.selected_display == display_type:
            return
        if self.selected_display not in (self.ALERT_PAGE, self.MESSAGE_PAGE):
            self.previous_display = self.selected_display
        if self.active_display:
            self.active_display.hide()
        self.selected_display = display_type
        self.active_display = self.display_list[display_type]
        # self.display_box.setText(self.display_list[self.DISPLAY_TYPES[self.__get_next_display_index()]].get_name())
        self.display_box.setText(self.active_display.get_name())
        print("Activating display '{}'".format(self.active_display.get_name()))
        self.active_display.show()

    def display_message(self, message: str):
        self.display_list[self.MESSAGE_PAGE].set_message(message)
        self.select_display(self.MESSAGE_PAGE)

    def select_previous_display(self):
        self.select_display(self.previous_display)

    def update_display(self):
        self.trigger_update_display = False
        # Switch to nearest page and alert if there is danger will
        if self.report_list.is_danger():
            self.select_display(self.NEAREST_PAGE)
            self.start_alarm()
        if self.alert_time > -1:
            self.select_display(self.ALERT_PAGE)
            time.sleep(0.2)
            self.select_previous_display()
            # if self.selected_display == self.ALERT_PAGE:
            #     self.select_display(self.NEAREST_PAGE)
            # else:
            if time.time() - self.alert_time > 10:
                # Blink for 10 seconds
                self.cancel_alarm()
                # self.select_display(self.NEAREST_PAGE)
        if self.active_display:
            self.active_display.update_display()

    def button_a_was_pressed(self):
        """
        Display specific button
        """
        if self.active_display:
            self.active_display.button_a_was_pressed()

    def __get_next_display_index(self):
        try:
            current_index = self.DISPLAY_TYPES.index(self.selected_display)
        except:
            return 0
        current_index += 1
        if current_index == len(self.DISPLAY_TYPES):
            current_index = 0
        return current_index

    def button_b_was_pressed(self):
        """
        Cycle next display
        """
        self.select_display(self.DISPLAY_TYPES[self.__get_next_display_index()])

    def button_c_was_pressed(self):
        if self.active_display:
            self.active_display.button_c_was_pressed()

    def start_alarm(self):
        self.alert_time = time.time()
        print("Starting alarm")

    def cancel_alarm(self):
        self.alert_time = -1
        print("Cancelling alarm")


class Display:
    def get_name(self):
        return ""

    def show(self):
        pass

    def hide(self):
        pass

    def update_display(self):
        pass

    def button_a_was_pressed(self):
        pass

    def button_c_was_pressed(self):
        pass


class AltitudeProfilePage(Display):
    def __init__(self, report_list, manager):
        self.report_list = report_list
        self.manager = manager
        self.x_range = 2  # minutes
        self.y_range = 2000  # feet
        self.cleared = False
        self.x_scale_box = M5TextBox(290, 3 + SCREEN_HEIGHT // 2, "", lcd.FONT_Default, 0xffffff)
        self.y_scale_box = M5TextBox(5, HEADER_OFFSET, "", lcd.FONT_Default, 0xffffff)
        self.zoom_out_box = M5TextBox(223, 225, "Out", lcd.FONT_Default, lcd.GREEN, rotate=0)
        self.zoom_in_box = M5TextBox(50, 225, "In", lcd.FONT_Default, lcd.GREEN, rotate=0)
        self.update_scale_boxes()
        self.hide()

    def get_name(self):
        return "Alt profile"

    def scale_y(self, y):
        y_offset = y / self.y_range
        return int(-y_offset * SCREEN_HEIGHT / 2 + SCREEN_HEIGHT / 2)

    def scale_x(self, x):
        x_offset = x / self.x_range
        return int(x_offset * SCREEN_WIDTH)

    def update_display(self):
        reports = self.report_list.get_selected_reports()
        if not self.cleared:
            self.redraw()
        if len(reports) == 0:
            return
        start_altitude = self.manager.situation_dictionary["OwnAltitude"]
        for report in reports:  # type: PositionReport
            self.cleared = False
            altitude_difference = report.altitude - start_altitude
            y = self.scale_y(altitude_difference)
            crossing_time = report.get_altitude_crossing_time()
            x = self.scale_x(crossing_time)
            if crossing_time == 99:
                # Crossing too far into the future, gives a horizontal line
                crossing_altitude = y
            else:
                crossing_altitude = SCREEN_HEIGHT // 2
            if x >= 0:
                # Crossing time is in the future
                x0 = 0
                y0 = y
                x1 = x
                y1 = crossing_altitude
            else:
                # Crossing time was in the past
                x0 = x
                y0 = crossing_altitude
                x1 = 0
                y1 = y
            x1, y1 = extend_line(x0, y0, x1, y1)
            x0, y0, x1, y1 = clip_line(x0, y0, x1, y1)

            if x0 is None:
                continue
            distance_fraction = 1 - min(report.get_distance() / 20, 1)  # Fraction of 20 nautical miles

            colour_grade = int(distance_fraction * 240) + 16
            colour = colour_grade * 255 * 255 + colour_grade * 255 + colour_grade
            lcd.line(x0, y0, x1, y1, color=colour)
            text_width = lcd.textWidth(str(report.identifier))
            if x1 >= SCREEN_WIDTH-1:
                lcd.font(lcd.FONT_DefaultSmall)
                lcd.print("{}".format(report.identifier), int(x1 - text_width), y1)
            else:
                lcd.font(lcd.FONT_DefaultSmall, rotate=90)

                lcd.print("{}".format(report.identifier), x1,
                          y1 if y1 < SCREEN_HEIGHT - FOOTER_OFFSET - text_width else y1 - text_width)

    def update_scale_boxes(self):
        self.x_scale_box.setText("{}m".format(self.x_range))
        self.y_scale_box.setText("{}ft".format(self.y_range))

    def clear(self):
        lcd.rect(0, HEADER_OFFSET, SCREEN_WIDTH, SCREEN_HEIGHT - FOOTER_OFFSET, lcd.BLACK, lcd.BLACK)
        self.cleared = True

    def redraw(self):
        self.clear()
        self.x_scale_box.show()
        self.y_scale_box.show()
        lcd.line(0, SCREEN_HEIGHT // 2, SCREEN_WIDTH, SCREEN_HEIGHT // 2, lcd.WHITE)
        lcd.line(0, HEADER_OFFSET, 0, SCREEN_HEIGHT - FOOTER_OFFSET, lcd.WHITE)

    def show(self):
        self.update_scale_boxes()
        self.x_scale_box.show()
        self.y_scale_box.show()
        self.zoom_in_box.show()
        self.zoom_out_box.show()
        self.redraw()

    def hide(self):
        self.x_scale_box.hide()
        self.y_scale_box.hide()
        self.zoom_in_box.hide()
        self.zoom_out_box.hide()
        self.clear()

    def update_zoom(self):
        self.update_scale_boxes()
        self.manager.trigger_update_display = True

    def button_a_was_pressed(self):
        if self.x_range == 1:
            return
        self.x_range -= 1
        self.y_range -= 1000
        self.update_zoom()

    def button_c_was_pressed(self):
        self.x_range += 1
        self.y_range += 1000
        self.update_zoom()


class SettingsPage(Display):
    ROW_SPACING = 25

    def __init__(self, report_list, manager):
        self.current_setting = -1
        self.report_list = report_list
        self.manager = manager
        self.setting_boxes = [
            (M5TextBox(0, 0 * self.ROW_SPACING + HEADER_OFFSET, "[ ]", lcd.FONT_Default, 0xffffff),
             M5TextBox(30, 0 * self.ROW_SPACING + HEADER_OFFSET, "", lcd.FONT_Default, 0xffffff),
             M5TextBox(223, 0 * self.ROW_SPACING + HEADER_OFFSET, "", lcd.FONT_Default, lcd.GREEN))
        ]
        self.settings = [
            ("Include valid:", self.report_list.toggle_include_valid_positions,
             self.report_list.get_include_valid_positions)
        ]
        self.load_settings()
        for index in range(len(self.setting_boxes)):
            self.setting_boxes[index][1].setText(self.settings[index][0])
            self.setting_boxes[index][2].setText("{}".format(self.settings[index][2]()))
        self.button_a_was_pressed()
        self.ok_box = M5TextBox(223, 225, "TOGGLE", lcd.FONT_Default, lcd.GREEN, rotate=0)
        self.down = M5TextBox(50, 225, "NEXT", lcd.FONT_Default, lcd.GREEN, rotate=0)
        self.toggled = False
        self.hide(store=False)

    def get_name(self):
        return "Settings"

    def show(self):
        self.toggled = False
        self.ok_box.show()
        self.down.show()
        for item in self.setting_boxes:
            item[0].show()
            item[1].show()
            item[2].show()

    def hide(self, store=True):
        self.ok_box.hide()
        self.down.hide()
        for item in self.setting_boxes:
            item[0].hide()
            item[1].hide()
            item[2].hide()
        if store and self.toggled:
            self.store_settings()

    def button_a_was_pressed(self):
        self.current_setting += 1
        if self.current_setting >= len(self.settings):
            self.current_setting = 0
        for item in self.setting_boxes:
            item[0].setText("[ ]")
        self.setting_boxes[self.current_setting][0].setText("[X]")

    def button_c_was_pressed(self):
        self.toggled = True
        self.settings[self.current_setting][1]()
        self.setting_boxes[self.current_setting][2].setText("{}".format(self.settings[self.current_setting][2]()))

    def store_settings(self):
        print("Storing settings")
        data = {}
        for item in self.settings:
            name, setter, getter = item
            data[name] = getter()
        with open("settings.json", "w") as o:
            json.dump(data, o)

    def load_settings(self):
        print("Loading settings")
        try:
            with open("settings.json", "r") as o:
                data = json.load(o)
        except:
            print("Failed loading file 'settings.json'")
            return
        for item in self.settings:
            name, setter, getter = item
            print("Checking setting {}".format(name))
            try:
                print("Setting {} to {}".format(name, data[name]))
                setter(data[name])
            except KeyError:
                print("Setting failed")


class AlertDisplay(Display):
    def __init__(self):
        self.alert_rectangle = M5Rect(0, 30, 320, 240 - HEADER_OFFSET - FOOTER_OFFSET, lcd.YELLOW, lcd.RED)
        self.hide()

    def get_name(self):
        return "Alert"

    def show(self):
        self.alert_rectangle.show()

    def hide(self):
        self.alert_rectangle.hide()


class NearestDisplay(Display):
    ROW_SPACING = 43
    ROW_OFFSET = 30

    def __init__(self, reports: "ReportList", manager):
        self.reports_list = reports
        self.manager = manager
        self.reports = []
        self.report = None
        self.visible = False
        self.font = lcd.FONT_DejaVu40
        self.background_colour = 0xFFFFFF
        self.alerting = False
        self.identifier = M5TextBox(40, 0 * self.ROW_SPACING + HEADER_OFFSET, "", self.font,
                                    lcd.MAGENTA,
                                    rotate=0)
        self.altitude_difference_header = M5TextBox(25, 1 * self.ROW_SPACING, "d ft",
                                                    lcd.FONT_Default,
                                                    self.background_colour,
                                                    rotate=0)
        self.vertical_speed_difference_header = M5TextBox(260, 1 * self.ROW_SPACING, "ft/m",
                                                          lcd.FONT_Default,
                                                          self.background_colour,
                                                          rotate=0)

        self.altitude_difference = M5TextBox(0, 1 * self.ROW_SPACING + HEADER_OFFSET, "",
                                             self.font,
                                             self.background_colour,
                                             rotate=0)
        self.vertical_speed = M5TextBox(200, 1 * self.ROW_SPACING + HEADER_OFFSET, "",
                                        self.font,
                                        self.background_colour,
                                        rotate=0)
        self.crossing_time = M5TextBox(100, 2 * self.ROW_SPACING + HEADER_OFFSET, "",
                                       self.font,
                                       self.background_colour,
                                       rotate=0)

        self.distance = M5TextBox(0, 3 * self.ROW_SPACING + HEADER_OFFSET, "",
                                  self.font,
                                  self.background_colour,
                                  rotate=0)

        self.age = M5TextBox(200, 3 * self.ROW_SPACING + HEADER_OFFSET, "", self.font,
                             self.background_colour,
                             rotate=0)
        self.hide()

    def get_name(self):
        return "NEAREST"

    def hide(self):
        self.visible = False
        self.identifier.hide()
        self.age.hide()
        self.altitude_difference_header.hide()
        self.vertical_speed_difference_header.hide()
        self.distance.hide()
        self.altitude_difference.hide()
        self.vertical_speed.hide()
        self.crossing_time.hide()

    def show(self):
        self.visible = True
        self.identifier.show()
        self.altitude_difference_header.show()
        self.vertical_speed_difference_header.show()
        self.vertical_speed.show()
        self.age.show()
        self.distance.show()
        self.altitude_difference.show()
        self.crossing_time.show()

    def update_display(self):
        self.reports = self.reports_list.get_list_sorted_score()
        if len(self.reports) == 0:
            self.hide()
            return
        self.show()
        self.report = self.reports[0]
        self.identifier.setText("{: ^10}".format(self.report.identifier))
        if self.report.is_good_distance():
            self.distance.setText("{:>.0f}nm".format(self.report.get_distance()))
        else:
            self.distance.setText("({:>.0f})nm".format(self.report.get_distance()))
        self.age.setText("{:>3.0f}s".format(self.report.get_age()))
        self.vertical_speed.setText("{}".format(self.report.vertical_velocity))
        self.altitude_difference.setText(
            "{:.0f}".format(self.report.altitude - self.manager.situation_dictionary["OwnAltitude"]))
        self.crossing_time.setText("c{:.1f}m".format(self.report.get_altitude_crossing_time()))

    def button_a_was_pressed(self):
        if self.alerting:
            self.manager.cancel_alarm()
        else:
            self.manager.start_alarm()


class ListDisplay(Display):
    ROW_SPACING = 50
    ROW_OFFSET = 30
    NUMBER_OF_ROWS = 4

    # 320 x 240
    def __init__(self, reports: "ReportList", manager):
        self.manager = manager
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
                M5TextBox(0, index * self.ROW_SPACING + HEADER_OFFSET, "", self.font, lcd.MAGENTA,
                          rotate=0),
                M5TextBox(120, index * self.ROW_SPACING + HEADER_OFFSET, "", self.font, self.background_colour,
                          rotate=0),
                M5TextBox(210, index * self.ROW_SPACING + HEADER_OFFSET, "", self.font, self.background_colour,
                          rotate=0),
                M5TextBox(0, index * self.ROW_SPACING + HEADER_OFFSET + int(self.ROW_SPACING / 2), "", self.font,
                          self.background_colour,
                          rotate=0),
                M5TextBox(150, index * self.ROW_SPACING + HEADER_OFFSET + int(self.ROW_SPACING / 2), "", self.font,
                          self.background_colour,
                          rotate=0),
                M5TextBox(250, index * self.ROW_SPACING + HEADER_OFFSET + int(self.ROW_SPACING / 2), "", self.font,
                          self.background_colour,
                          rotate=0)
            ))
        self.page_box = M5TextBox(50, 225, "1/0", lcd.FONT_Default, lcd.GREEN, rotate=0)
        self.hide()

    def get_name(self):
        return "LIST"

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

    def display_report(self, report: "LatestReport", index: int):
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

    def button_a_was_pressed(self):
        self.current_page += 1
        if self.current_page >= self.number_of_pages:
            self.current_page = 0
        self.manager.trigger_update_display = True
