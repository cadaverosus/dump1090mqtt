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
    line = line.strip()
    columns = line.split(',')
    message_type = columns[0]
    hex_code = columns[4]
    now = datetime.now()

    if valid_hex(hex_code):
        if hex_code not in airplanes:
            airplanes[hex_code] = {
                "flight_number": None,
                "tail_number": None,
                "location": None,
                "altitude": None,
                "speed": None,
                "vertical_rate": None,
                "squawk": None,
                "emergency": None,
                "last_sent": None,
            }
        airplane = airplanes[hex_code]

        if message_type in ["MSG", "ID"] and valid_flight_number(columns[10]):
            airplane["flight_number"] = columns[10]

        if message_type == "MSG" and columns[1] == "3" and valid_location(columns[14], columns[15]):
            airplane["location"] = f"{float(columns[14])},{float(columns[15])}"

        if message_type == "MSG" and columns[1] == "4":
            airplane["altitude"], airplane["speed"], airplane["vertical_rate"] = convert_to_metric(
                float(columns[11]) if columns[11] else None,
                float(columns[12]) if columns[12] else None,
                float(columns[16]) if columns[16] else None,
            )

        if message_type == "MSG" and columns[1] == "1":
            airplane["tail_number"] = columns[10]

        if message_type == "MSG" and (columns[1] == "5" or columns[1] == "6"):
            airplane["squawk"] = columns[10]
            airplane["emergency"] = columns[14]

        if (
            airplane["flight_number"] is not None
            and airplane["location"] is not None
            and airplane["tail_number"] is not None
            and (airplane["last_sent"] is None or now - airplane["last_sent"] >= timedelta(minutes=3))
        ):
            payload = f"{airplane['altitude'] or ''},{airplane['speed'] or ''},{airplane['vertical_rate'] or ''},{airplane['squawk'] or ''},{airplane['emergency'] or ''}"
            message = {
                "topic": f"/adsb/{radar}/{hex_code}/{airplane['flight_number']}/{airplane['tail_number']}/{airplane['location']}",
                "payload": payload.strip(','),
            }
            airplane["last_sent"] = now
            return message
    else:
        print(f"Invalid hex code: {hex_code}")
    return None

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
        message = parse_data(radar, line, airplanes)
        if message is not None:
            ttc.publish(message['topic'], message['payload'])
            if options.console:
                print(message['topic'], message['payload'])
        line = socket_file.readline()

    ttc.disconnect()
    socket_file.close()
    feeder_socket.close()

if __name__ == '__main__':
    publish()

