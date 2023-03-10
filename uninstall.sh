#!/bin/bash

rm /service/dbus-solax-x1-pvinverter
kill $(pgrep -f 'supervise dbus-solax-x1-pvinverter')
chmod a-x /data/dbus-solax-x1-pvinverter/service/run
./restart.sh
