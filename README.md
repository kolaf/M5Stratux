# M5Stratux
M5stack interface to Stratux

M5Stratux is a simple interface to the Stratux to allow display of position less contacts. It is meant as a supplement 
to an EFB which will handle contacts with positions. However, contacts without a position will be ignored by the EFB 
(typically). The purpose of M5Stratux is therefore to display information about estimated distance, altitude, and 
vertical velocity of contacts that have not reported their position to the receiver (either ADS-B contacts that have 
 and not sent this information yet, or Mode A/C contacts).
 
![Contact list view](/media/screenshot.jpg)

## Installation
This application requires that the M5stack runs the UIFlow firmware. This can be installed using the M5Burner from this 
location: https://m5stack.com/pages/download. When running M5Burner, select the latest version of UIFlow.

Install ampy to interact with the M5Stack over the USB serial link
```
pip install adafruit-ampy
```
Use ampy to load the code onto the device after blushing the firmware above. This step is a bit fiddly and requires 
precise timing between resetting the device and issuing the command.
```
cd src
ampy -p <serial_device> put uwebsockets /flash/uwebsockets
ampy -p <serial_device> put display_manager.py
ampy -p <serial_device> put report.py
ampy -p <serial_device> put main.py
```
Reset the device.

## What it does
Upon boot who tries to connect to the Stratux SSID "stratux" and connects to the websocket service at 192.168.10.1.

Incoming messages will are stored and displayed on several different view screens:
### List
Shows a paged list of all detected aeroplanes
### Details
Shows a more detailed view of individual records
### Nearest
Shows a blown up view of the nearest/most threatening contact
### Settings
A settings screen That a large toggling whether the device should display contacts with a a valid position (presumably 
these are handled by an EFB), or should only display contacts without a valid position. Settings are saved when exiting 
the screen.

## Simple user interface
The left button is always context sensitive to the current screen being displayed.

The middle button will always select the next screen (the name of the next screen is displayed over the button).

The right button is context sensitive, currently only used for the settings screen.

## Danger estimation
Since the distance estimate is unreliable, the best metric I come up with for doing estimation is the following:

```
def get_distance_score(self) -> float:
    minutes_until_altitude_crossing = self.get_altitude_crossing_time()
    if minutes_until_altitude_crossing< 0.5:
        minutes_until_altitude_crossing = 10
    score = math.fabs(minutes_until_altitude_crossing) * self.get_distance() * math.fabs(
        self.report_list.situation_dictionary["OwnAltitude"] - self.altitude) / 100000
    return score
```

## List view explained
![List view explained](/media/screenshot_explained.jpg)
