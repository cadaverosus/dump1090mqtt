#!/bin/sh

$(dirname $0)/dump1090pub.py -m $MQTT_HOST -p $MQTT_PORT -u $MQTT_USER -a $MQTT_PASS -H $DUMP1090_HOST -P $DUMP1090_PORT -r $RADARNAME
