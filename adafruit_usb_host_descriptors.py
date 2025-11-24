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

_RECIP_INTERFACE = const(1)

# No const because these are public
DESC_DEVICE = 0x01
DESC_CONFIGURATION = 0x02
DESC_STRING = 0x03
DESC_INTERFACE = 0x04
DESC_ENDPOINT = 0x05
DESC_HID = 0x21
DESC_REPORT = 0x22

INTERFACE_HID = 0x03
SUBCLASS_BOOT = 0x01
SUBCLASS_REPORT = None
PROTOCOL_MOUSE = 0x02
PROTOCOL_KEYBOARD = 0x01

# --- HID Report Descriptor Item Tags (The "Command") ---
HID_TAG_USAGE_PAGE = 0x05  # Defines the category (e.g., Generic Desktop, Game Controls)
HID_TAG_USAGE = 0x09  # Defines the specific item (e.g., Mouse, Joystick)

# --- Usage Page IDs (Values for 0x05) ---
USAGE_PAGE_GENERIC_DESKTOP = 0x01

# --- Usage IDs (Values for 0x09, inside Generic Desktop) ---
USAGE_MOUSE = 0x02
USAGE_JOYSTICK = 0x04
USAGE_GAMEPAD = 0x05
USAGE_KEYBOARD = 0x06


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


def get_report_descriptor(device, interface_num, length):
    """
    Fetches the HID Report Descriptor.
    This tells us what the device actually IS (Mouse vs Joystick).
    """
    if length < 1:
        return None

    buf = bytearray(length)
    try:
        # 0x81 = Dir: IN | Type: Standard | Recipient: Interface
        # wValue = 0x2200 (Report Descriptor)
        device.ctrl_transfer(
            _RECIP_INTERFACE | _REQ_TYPE_STANDARD | _DIR_IN,
            _REQ_GET_DESCRIPTOR,
            DESC_REPORT << 8,
            interface_num,
            buf,
        )
        return buf
    except Exception as e:
        print(f"Failed to read Report Descriptor: {e}")
        return None


def _is_confirmed_mouse(report_desc):
    """
    Scans the raw descriptor bytes for:
    Usage Page (Generic Desktop) = 0x05, 0x01
    Usage (Mouse)                = 0x09, 0x02
    """
    if not report_desc:
        return False

    # Simple byte scan check
    # We look for Usage Page Generic Desktop (0x05 0x01)
    has_generic_desktop = False
    for i in range(len(report_desc) - 1):
        if (
            report_desc[i] == HID_TAG_USAGE_PAGE
            and report_desc[i + 1] == USAGE_PAGE_GENERIC_DESKTOP
        ):
            has_generic_desktop = True

    # We look for Usage Mouse (0x09 0x02)
    has_mouse_usage = False
    for i in range(len(report_desc) - 1):
        if report_desc[i] == HID_TAG_USAGE and report_desc[i + 1] == USAGE_MOUSE:
            has_mouse_usage = True

    return has_generic_desktop and has_mouse_usage


def _find_endpoint(device, protocol_type: Literal[PROTOCOL_MOUSE, PROTOCOL_KEYBOARD], subclass):
    config_descriptor = get_configuration_descriptor(device, 0)
    i = 0
    mouse_interface_index = None
    found_mouse = False
    candidate_found = False
    hid_desc_len = 0
    while i < len(config_descriptor):
        descriptor_len = config_descriptor[i]
        descriptor_type = config_descriptor[i + 1]

        # Found Interface
        if descriptor_type == DESC_INTERFACE:
            interface_number = config_descriptor[i + 2]
            interface_class = config_descriptor[i + 5]
            interface_subclass = config_descriptor[i + 6]
            interface_protocol = config_descriptor[i + 7]

            # Reset checks
            candidate_found = False
            hid_desc_len = 0

            # Found mouse or keyboard interface depending on what was requested
            if (
                interface_class == INTERFACE_HID
                and interface_protocol == protocol_type
                and interface_subclass == SUBCLASS_BOOT
                and subclass == SUBCLASS_BOOT
            ):
                found_mouse = True
                mouse_interface_index = interface_number

            # May be trackpad interface if it's not a keyboard and looking for mouse
            elif (
                interface_class == INTERFACE_HID
                and interface_protocol != PROTOCOL_KEYBOARD
                and protocol_type == PROTOCOL_MOUSE
                and subclass != SUBCLASS_BOOT
            ):
                candidate_found = True

        # Found HID Descriptor (Contains Report Length)
        elif descriptor_type == DESC_HID and candidate_found:
            # The HID descriptor stores the Report Descriptor length at offset 7
            # Bytes: [Length, Type, BCD, BCD, Country, Count, ReportType, ReportLenL, ReportLenH]
            if descriptor_len >= 9:
                hid_desc_len = config_descriptor[i + 7] + (config_descriptor[i + 8] << 8)

        elif descriptor_type == DESC_ENDPOINT:
            endpoint_address = config_descriptor[i + 2]
            if endpoint_address & _DIR_IN:
                if found_mouse:
                    return mouse_interface_index, endpoint_address

                elif candidate_found:
                    print(f"Checking Interface {interface_number}...")
                    rep_desc = get_report_descriptor(device, interface_number, hid_desc_len)
                    if _is_confirmed_mouse(rep_desc):
                        print(f" -> CONFIRMED: It is a Mouse/Trackpad (Usage 0x09 0x02)")
                        return interface_number, endpoint_address

                    candidate_found = False  # Stop looking at this interface

        i += descriptor_len
    return None, None


def find_boot_mouse_endpoint(device):
    """
    Try to find a boot mouse endpoint in the device and return its
    interface index, and endpoint address.
    :param device: The device to search within
    :return: mouse_interface_index, mouse_endpoint_address if found, or None, None otherwise
    """
    return _find_endpoint(device, PROTOCOL_MOUSE, SUBCLASS_BOOT)


def find_report_mouse_endpoint(device):
    """
    Try to find a report mouse endpoint in the device and return its
    interface index, and endpoint address.
    :param device: The device to search within
    :return: mouse_interface_index, mouse_endpoint_address if found, or None, None otherwise
    """
    return _find_endpoint(device, PROTOCOL_MOUSE, SUBCLASS_REPORT)


def find_boot_keyboard_endpoint(device):
    """
    Try to find a boot keyboard endpoint in the device and return its
    interface index, and endpoint address.
    :param device: The device to search within
    :return: keyboard_interface_index, keyboard_endpoint_address if found, or None, None otherwise
    """
    return _find_endpoint(device, PROTOCOL_KEYBOARD, SUBCLASS_BOOT)
