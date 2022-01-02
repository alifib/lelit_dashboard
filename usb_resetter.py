#!/usr/bin/env python
import fcntl
import os
from subprocess import Popen, PIPE

USBDEVFS_RESET = 21780


def reset_usb(driver: str):
    try:
        print("resetting driver:", driver)
        lsusb = Popen(f"lsusb | grep -i {driver}", shell=True, bufsize=64, stdin=PIPE, stdout=PIPE,
                      close_fds=True).stdout.read().strip().split()
        bus = lsusb[1].decode()
        device = lsusb[3][:-1].decode()
        with open(f'/dev/bus/usb/{bus}/{device}', 'w', os.O_WRONLY) as f:
            fcntl.ioctl(f, USBDEVFS_RESET, 0)
        print(f'Reset completed on bus {bus}, device ID {device}.')
    except Exception as e:
        print('failed to reset device:', e)
        raise
