# SPDX-FileCopyrightText: Copyright (c) 2025 Tim Cocks for Adafruit Industries
#
# SPDX-License-Identifier: MIT
import array

import usb

import adafruit_usb_host_descriptors

# lists for mouse interface indexes, endpoint addresses, and USB Device instances
# each of these will end up with length 2 once we find both mice
mouse_interface_indexes = None
mouse_endpoint_addresses = None
keyboard = None

# scan for connected USB devices
for device in usb.core.find(find_all=True):
    # check for boot mouse endpoints on this device
    kbd_interface_index, kbd_endpoint_address = (
        adafruit_usb_host_descriptors.find_boot_keyboard_endpoint(device)
    )
    # if a boot mouse interface index and endpoint address were found
    if kbd_interface_index is not None and kbd_interface_index is not None:
        keyboard = device

        # detach device from kernel if needed
        if keyboard.is_kernel_driver_active(0):
            keyboard.detach_kernel_driver(0)

        # set the mouse configuration so it can be used
        keyboard.set_configuration()

buf = array.array("b", [0] * 8)

while True:
    # try to read data from the mouse
    try:
        count = keyboard.read(mouse_endpoint_addresses, buf, timeout=10)

    # if there is no data it will raise USBTimeoutError
    except usb.core.USBTimeoutError:
        # Nothing to do if there is no data for this mouse
        continue

    for b in buf:
        print(hex(b), end=" ")
    print()
