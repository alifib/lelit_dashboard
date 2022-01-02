#!/usr/bin/env python
import json
import os
import time
from abc import abstractmethod
from enum import Enum

import psutil
from influxdb import InfluxDBClient
from serial import Serial

from usb_resetter import reset_usb

with open('config.json', 'r') as conf:
    influx_conf = json.load(conf)['influx']


class InfluxReporter:
    BODY_TEMPLATE = {
        "measurement": '',
        "fields": dict()
    }

    def __init__(self):
        self._client = None
        self.measurement_name = None

    @property
    def client(self):
        # connect to influx
        if self._client is None:
            self._client = InfluxDBClient(influx_conf['host'],
                                          influx_conf['port'],
                                          influx_conf['user'],
                                          influx_conf['pass'],
                                          influx_conf['db'])
        return self._client

    @abstractmethod
    def collect_and_report(self):
        raise NotImplementedError()

    def do_report(self, fields: dict):
        body = self.BODY_TEMPLATE.copy()
        body['measurement'] = self.measurement_name
        body['fields'] = fields
        self.client.write_points([body])


class StatsReporter(InfluxReporter):
    def __init__(self):
        super().__init__()
        self.measurement_name = 'system'

    def collect_and_report(self):
        # collect some stats from psutil
        disk = psutil.disk_usage('/')
        mem = psutil.virtual_memory()
        load = psutil.getloadavg()
        fields = {
            "load_1": load[0],
            "load_5": load[1],
            "load_15": load[2],
            "disk_percent": disk.percent,
            "disk_free": disk.free,
            "disk_used": disk.used,
            "mem_percent": mem.percent,
            "mem_free": mem.free,
            "mem_used": mem.used
        }
        self.do_report(fields)


class LelitReporter(InfluxReporter):
    class MaraXMode(Enum):
        BrewPriority = 'C'
        SteamPriority = 'V'

    TTY_NAME = 'ttyUSB'
    BAUDRATE = 9600
    HOUR = 60 * 60
    RESET_INTERVAL = 1 * HOUR
    DRIVER_NAME = 'CH340'  # change this to the driver your OS using. to know your driver, run "lsusb" on your
    # environment and not the line of the driver for your usb-to-serial device.

    def __init__(self):
        super().__init__()
        self.serial = Serial(self.find_tty(), self.BAUDRATE)
        self.measurement_name = 'lelit'
        self.last_reset = None
        self.reset_if_needed()

    def find_tty(self):
        for file in os.listdir("/dev/"):
            if self.TTY_NAME in file:
                return os.path.join("/dev", file)

    def parse(self, items) -> dict:
        try:
            mode_and_version = items[0]
            mode = self.MaraXMode(mode_and_version[0])
            version = mode_and_version[1:]
            actual_temp, target_temp, actual_hx_temp, countdown, heating_element_state = [int(i) for i in items[1:]]
            fields = {
                'mode': mode.name,
                'version': version,
                'actual_temp': actual_temp,
                'target_temp': target_temp,
                'actual_hx_temp': actual_hx_temp,
                'countdown': countdown,
                'heating_element_state': bool(heating_element_state)
            }
            return fields
        except Exception:
            raise ValueError()

    def collect_and_report(self):
        self.reset_if_needed()
        try:
            line = self.serial.readline().decode()
            items = line.split(',')
            items[-1] = items[-1].replace('\r\n', '')
            fields = self.parse(items)
        except (UnicodeDecodeError, ValueError):
            fields = {'error': 1}
        print('sending: ', end='')
        print(fields)

        self.do_report(fields)

    def line_reader(self):
        while self.serial.readable():
            yield self.serial.readline()

    def reset_if_needed(self):
        if self.last_reset is None or time.time() - self.last_reset > self.RESET_INTERVAL:
            self._reset_usb()

    def _reset_usb(self):
        try:
            reset_usb(self.DRIVER_NAME)
        except Exception:
            pass
        else:
            self.last_reset = time.time()


if __name__ == '__main__':
    reporters = [StatsReporter(), LelitReporter()]
    while True:
        for reporter in reporters:
            reporter.collect_and_report()
        time.sleep(1)
