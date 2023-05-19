#!/usr/bin/env python3
"""
Publish dump1090 output to MQTT
"""

from socket import socket, AF_INET, SOCK_STREAM
from datetime import datetime, timedelta
import paho.mqtt.client as paho


def convert_to_metric(altitude, speed, vertical_rate):
    # 1 foot = 0.3048 meters
    # 1 knot = 0.514444 m/s
    altitude_meters = altitude * 0.3048 if altitude else None
    speed_ms = speed * 0.514444 if speed else None
    vertical_rate_ms = vertical_rate * 0.514444 if vertical_rate else None
    return altitude_meters, speed_ms, vertical_rate_ms

def valid_hex(hex_code):
    try:
        int(hex_code, 16)
        return True
    except ValueError:
        return False

def valid_flight_number(flight_number):
    # add your flight number validation logic here
    return True

def valid_location(lat, lon):
    try:
        lat = float(lat)
        lon = float(lon)
        return -90 <= lat <= 90 and -180 <= lon <= 180
    except ValueError:
        return False

def parse_data(radar, line, airplanes):
    fields = line.split(",")
    message_type = fields[0]
    hex_code = fields[4]
    now = datetime.now()

    if hex_code not in airplanes:
        airplanes[hex_code] = {"last_sent": None}

    airplane = airplanes[hex_code]

    if message_type == "MSG":
        if fields[1] == "1":
            airplane["flight_number"] = fields[10].strip()
        elif fields[1] == "3":
            airplane["altitude"] = fields[11]
            airplane["location"] = f"{fields[14]},{fields[15]}"
        elif fields[1] == "4":
            airplane["speed"] = fields[12]
            airplane["heading"] = fields[13]
            airplane["vertical_rate"] = fields[16]
        elif fields[1] == "5":
            airplane["squawk"] = fields[17]
    elif message_type == "STA" or message_type == "AIR":
        airplane["hex_code"] = hex_code

    if all(key in airplane for key in ["flight_number", "location"]):
        if airplane["last_sent"] is None or now - airplane["last_sent"] >= timedelta(minutes=3):
            airplane["last_sent"] = now
            topic = f"adsb/{radar}"
            message_parts = [
                hex_code,
                airplane["flight_number"],
                airplane["location"],
                airplane.get("altitude", "None"),
                airplane.get("speed", "None"),
                airplane.get("heading", "None"),
                airplane.get("vertical_rate", "None"),
                airplane.get("squawk", "None"),
            ]
            message = ",".join(message_parts)
            return topic, message

    return None, None

def parse_options():
    """parse command line options
    Return:
      (options, args)
    """

    from optparse import OptionParser
    parser = OptionParser()
    parser.add_option('-m', '--mqtt-host', dest='mqtt_host',
                      help="MQTT broker hostname", default='127.0.0.1')
    parser.add_option('-p', '--mqtt-port', dest='mqtt_port', type="int",
                      help="MQTT broker port number", default=1883)
    parser.add_option('-u', '--mqtt-user', dest='mqtt_user',
                      help="MQTT broker connect user", default='')
    parser.add_option('-a', '--mqtt-password', dest='mqtt_password',
                      help="MQTT broker connert password", default='')
    parser.add_option('-H', '--dump1090-host', dest='dump1090_host',
                      help="dump1090 hostname", default='127.0.0.1')
    parser.add_option('-P', '--dump1090-port', dest='dump1090_port', type="int",
                      help="dump1090 port number", default=30003)
    parser.add_option('-r', '--radar-name', dest='radar',
                      help="name of radar. used as topic string /adsb/RADAR/icaoaddr",
                      metavar='RADAR')
    parser.add_option('-c', '--console', dest='console', action="store_true",
                      help="write out topic and payload to console")
    return parser.parse_args()

def publish():
    """publish to topic /radar/icioaddr with ADS-B feed read from socket"""

    (options, _) = parse_options()

    airplanes = {}
    ttc = paho.Client()
    if options.mqtt_user != '':
        ttc.username_pw_set(options.mqtt_user, password=options.mqtt_password)
    ttc.connect(options.mqtt_host, options.mqtt_port)

    feeder_socket = socket(AF_INET, SOCK_STREAM)
    feeder_socket.connect((options.dump1090_host, options.dump1090_port))
    socket_file = feeder_socket.makefile()

    line = socket_file.readline()
    while line:
        topic, message = parse_data(options.radar, line, airplanes)
        if topic is not None and message is not None:
            ttc.publish(topic, message)
            if options.console:
                print(topic, message)
        line = socket_file.readline()

    ttc.disconnect()
    socket_file.close()
    feeder_socket.close()

if __name__ == '__main__':
    publish()

