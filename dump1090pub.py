#!/usr/bin/env python3
"""
Publish dump1090 output to MQTT
"""

from socket import socket, AF_INET, SOCK_STREAM
from datetime import datetime, timedelta
import threading
import json
import paho.mqtt.client as paho
import time


def convert_to_metric(altitude=None, speed=None, vertical_rate=None):
    feet_to_meters = 0.3048
    knots_to_kmh = 1.852
    fpm_to_ms = 0.00508

    altitude_meters = int(altitude * feet_to_meters) if altitude is not None else None
    speed_kmh = int(speed * knots_to_kmh) if speed is not None else None
    vertical_rate_ms = int(vertical_rate * fpm_to_ms) if vertical_rate is not None else None

    return altitude_meters, speed_kmh, vertical_rate_ms

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

def parse_data(radar, line, airplane):
    fields = line.split(",")
    message_type = fields[0]
    hex_code = fields[4]
    if "location" in airplane:
        prev_location = airplane["location"]
    else:
        prev_location = None

    if message_type == "MSG":
        if fields[1] == "1":
            airplane["flight_number"] = fields[10].strip()
        elif fields[1] == "3":
            altitude, _, _ = convert_to_metric(altitude=float(fields[11]) if fields[11] else None)
            airplane["altitude"] = altitude
            airplane["location"] = f"{fields[14]},{fields[15]}"
        elif fields[1] == "4":
            _, speed, vertical_rate = convert_to_metric(
                speed=float(fields[12]) if fields[12] else None,
                vertical_rate=float(fields[16]) if fields[16] else None
            )
            airplane["speed"] = speed
            airplane["vertical_rate"] = vertical_rate
            airplane["heading"] = int(float(f"{fields[13]}")) if fields[13] else None
        elif fields[1] == "5":
            airplane["squawk"] = fields[17] if fields[17] else "None"
    elif message_type == "STA" or message_type == "AIR":
        airplane["hex_code"] = hex_code

    if prev_location:
        if airplane["location"] == prev_location:
            #print('same location ' + hex_code)
            return airplane["location"], None, None
    if all(key in airplane for key in ["flight_number", "location"]):
        topic = f"adsb/{radar}/update"
        message = {
            "icao_hex": hex_code,
            "icao_flight_number": airplane["flight_number"],
            "location": airplane["location"],
            "altitude_m": airplane.get("altitude", "None"),
            "speed_kmh": airplane.get("speed", "None"),
            "heading": airplane.get("heading", "None"),
            "vertical_rate_ms": airplane.get("vertical_rate", "None"),
            "squawk": airplane.get("squawk", "None"),
        }
        # message = ",".join(message_parts)
        #message = ",".join(str(part) for part in message_parts)
        payload = json.dumps(message)
        return airplane["location"], topic, payload

    return None, None, None

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

class Publisher:
    def __init__(self):
        (options, _) = parse_options()

        self.ttc = paho.Client()
        if options.mqtt_user != '':
            self.ttc.username_pw_set(options.mqtt_user, password=options.mqtt_password)
        self.ttc.connect(options.mqtt_host, options.mqtt_port)

        self.feeder_socket = socket(AF_INET, SOCK_STREAM)
        self.feeder_socket.connect((options.dump1090_host, options.dump1090_port))
        self.socket_file = self.feeder_socket.makefile()

        self.radar = options.radar
        if options.console:
            self.console = True
        self.shutdown_flag = False

    def start_status_loop(self, interval):
        while not self.shutdown_flag:
            topic = f"adsb/{self.radar}/status"
            message = f"ok"
            self.ttc.publish(topic, message)
            print(f"{topic}, {message}")
            time.sleep(interval)

    def publish(self):
        """publish to topic /radar/icioaddr with ADS-B feed read from socket"""

        airplanes = {}

        line = self.socket_file.readline()
        while line:
            fields = line.split(",")
            hex_code = fields[4]
            if hex_code not in airplanes:
                airplanes[hex_code] = {"last_sent": None}
            airplane = airplanes[hex_code]

            location, topic, message = parse_data(self.radar, line, airplane)
            now = datetime.now()
            if topic is not None and message is not None:
                if airplane["last_sent"] is None or now - airplane["last_sent"] >= timedelta(seconds=30):
                    airplane["last_sent"] = now
                    airplane["location"] = location
                    self.ttc.publish(topic, message)
                    if self.console:
                        print(f"{topic}, {message}")

            line = self.socket_file.readline()
            if self.shutdown_flag:
                break

    def cleanup(self):
        if self.socket_file:
            self.socket_file.close()
        if self.feeder_socket:
            self.feeder_socket.close()
        if self.ttc:
            self.ttc.disconnect()

if __name__ == '__main__':
    publisher = Publisher()
    try:
        status_thread = threading.Thread(target=publisher.start_status_loop, args=(60,))
        status_thread.start()
        publisher.publish()
    except KeyboardInterrupt:
        print("\nCtrl+C received. Disconnecting and closing sockets...")
        publisher.shutdown_flag = True
        status_thread.join()
