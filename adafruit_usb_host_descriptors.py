# SPDX-FileCopyrightText: Copyright (c) 2023 Scott Shawcroft for Adafruit Industries
#
# SPDX-License-Identifier: MIT
"""
`adafruit_usb_host_descriptors`
================================================================================

Helpers for getting USB descriptors

* Author(s): Scott Shawcroft
"""

import struct

from micropython import const

try:
    from typing import Literal
except ImportError:
    pass

__version__ = "0.0.0+auto.0"
__repo__ = "https://github.com/adafruit/Adafruit_CircuitPython_USB_Host_Descriptors.git"


# USB defines
# Use const for these internal values so that they are inlined with mpy-cross.
_DIR_OUT = const(0x00)
_DIR_IN = const(0x80)

_REQ_RCPT_DEVICE = const(0)

_REQ_TYPE_STANDARD = const(0x00)

_REQ_GET_DESCRIPTOR = const(6)

# No const because these are public
DESC_DEVICE = 0x01
DESC_CONFIGURATION = 0x02
DESC_STRING = 0x03
DESC_INTERFACE = 0x04
DESC_ENDPOINT = 0x05

INTERFACE_HID = 0x03
SUBCLASS_BOOT = 0x01
PROTOCOL_MOUSE = 0x02
PROTOCOL_KEYBOARD = 0x01


def get_descriptor(device, desc_type, index, buf, language_id=0):
    """Fetch the descriptor from the device into buf."""
    # Allow capitalization that matches the USB spec.
    # pylint: disable=invalid-name
    wValue = desc_type << 8 | index
    wIndex = language_id
    device.ctrl_transfer(
        _REQ_RCPT_DEVICE | _REQ_TYPE_STANDARD | _DIR_IN,
        _REQ_GET_DESCRIPTOR,
        wValue,
        wIndex,
        buf,
    )


def get_device_descriptor(device):
    """Fetch the device descriptor and return it."""
    buf = bytearray(1)
    get_descriptor(device, DESC_DEVICE, 0, buf)
    full_buf = bytearray(buf[0])
    get_descriptor(device, DESC_DEVICE, 0, full_buf)
    return full_buf


def get_configuration_descriptor(device, index):
    """Fetch the configuration descriptor, its associated descriptors and return it."""
    # Allow capitalization that matches the USB spec.
    # pylint: disable=invalid-name
    buf = bytearray(4)
    get_descriptor(device, DESC_CONFIGURATION, index, buf)
    wTotalLength = struct.unpack("<xxH", buf)[0]
    full_buf = bytearray(wTotalLength)
    get_descriptor(device, DESC_CONFIGURATION, index, full_buf)
    return full_buf


def _find_boot_endpoint(device, protocol_type: Literal[PROTOCOL_MOUSE, PROTOCOL_KEYBOARD]):
    config_descriptor = get_configuration_descriptor(device, 0)
    i = 0
    mouse_interface_index = None
    found_mouse = False
    while i < len(config_descriptor):
        descriptor_len = config_descriptor[i]
        descriptor_type = config_descriptor[i + 1]
        if descriptor_type == DESC_INTERFACE:
            interface_number = config_descriptor[i + 2]
            interface_class = config_descriptor[i + 5]
            interface_subclass = config_descriptor[i + 6]
            interface_protocol = config_descriptor[i + 7]
            if (
                interface_class == INTERFACE_HID
                and interface_subclass == SUBCLASS_BOOT
                and interface_protocol == protocol_type
            ):
                found_mouse = True
                mouse_interface_index = interface_number

        elif descriptor_type == DESC_ENDPOINT:
            endpoint_address = config_descriptor[i + 2]
            if endpoint_address & _DIR_IN:
                if found_mouse:
                    return mouse_interface_index, endpoint_address
        i += descriptor_len
    return None, None


def find_boot_mouse_endpoint(device):
    """
    Try to find a boot mouse endpoint in the device and return its
    interface index, and endpoint address.
    :param device: The device to search within
    :return: mouse_interface_index, mouse_endpoint_address if found, or None, None otherwise
    """
    return _find_boot_endpoint(device, PROTOCOL_MOUSE)


def find_boot_keyboard_endpoint(device):
    """
    Try to find a boot keyboard endpoint in the device and return its
    interface index, and endpoint address.
    :param device: The device to search within
    :return: keyboard_interface_index, keyboard_endpoint_address if found, or None, None otherwise
    """
    return _find_boot_endpoint(device, PROTOCOL_KEYBOARD)
