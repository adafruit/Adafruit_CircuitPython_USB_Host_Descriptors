# SPDX-FileCopyrightText: Copyright (c) 2023 Scott Shawcroft for Adafruit Industries
#
# SPDX-License-Identifier: MIT
"""
`adafruit_usb_host_descriptors`
================================================================================

Helpers for getting USB descriptors

* Author(s): Scott Shawcroft
"""

import array
import struct

import usb
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
SUBCLASS_RESERVED = 0x00
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

INTERFACE_AUDIO = 0x01
SUBCLASS_AUDIO_STREAMING = 0x02

# USB Audio Class 1.0 descriptor values
_PROTOCOL_UAC2 = const(0x20)
_DESC_CS_INTERFACE = const(0x24)
_DESC_CS_ENDPOINT = const(0x25)
_AS_GENERAL = const(0x01)
_AS_FORMAT_TYPE = const(0x02)
_FORMAT_TYPE_I = const(0x01)
_FORMAT_PCM = const(0x0001)
_FORMAT_PCM8 = const(0x0002)
_EP_SAMPLING_FREQ_CONTROL = const(0x01)
_EP_ISOCHRONOUS = const(0x01)


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
    buf = array.array("B", bytearray(1))
    get_descriptor(device, DESC_DEVICE, 0, buf)
    full_buf = array.array("B", bytearray(buf[0]))
    get_descriptor(device, DESC_DEVICE, 0, full_buf)
    return bytearray(full_buf)


def get_configuration_descriptor(device, index):
    """Fetch the configuration descriptor, its associated descriptors and return it."""
    # Allow capitalization that matches the USB spec.
    # pylint: disable=invalid-name
    buf = array.array("B", bytearray(4))
    get_descriptor(device, DESC_CONFIGURATION, index, buf)
    wTotalLength = struct.unpack("<xxH", buf)[0]
    full_buf = array.array("B", bytearray(wTotalLength))
    get_descriptor(device, DESC_CONFIGURATION, index, full_buf)
    return bytearray(full_buf)


def get_report_descriptor(device, interface_num, length):
    """
    Fetches the HID Report Descriptor.
    This tells us what the device actually IS (Mouse vs Joystick).
    """
    if length < 1:
        return None

    buf = array.array("B", bytearray(length))
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
        return bytearray(buf)
    except usb.core.USBError as e:
        print(f"Failed to read Report Descriptor: {e}")
        return None


def _is_confirmed_usage(report_desc, usage_type):
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
    has_usage_type = False
    for i in range(len(report_desc) - 1):
        if report_desc[i] == HID_TAG_USAGE and report_desc[i + 1] == usage_type:
            has_usage_type = True

    return has_generic_desktop and has_usage_type


def _find_endpoint(
    device,
    protocol_type: Literal[PROTOCOL_MOUSE, PROTOCOL_KEYBOARD],
    subclass,
    usage_type: Literal[USAGE_MOUSE, USAGE_KEYBOARD, USAGE_GAMEPAD, USAGE_JOYSTICK] = USAGE_MOUSE,
):
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

            # Found mouse or keyboard depending on what was requested
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
                and subclass == SUBCLASS_RESERVED
            ):
                candidate_found = True
                mouse_interface_index = interface_number

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
                    rep_desc = get_report_descriptor(device, mouse_interface_index, hid_desc_len)
                    if _is_confirmed_usage(rep_desc, usage_type):
                        return mouse_interface_index, endpoint_address

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
    return _find_endpoint(device, PROTOCOL_MOUSE, SUBCLASS_RESERVED)


def find_boot_keyboard_endpoint(device):
    """
    Try to find a boot keyboard endpoint in the device and return its
    interface index, and endpoint address.
    :param device: The device to search within
    :return: keyboard_interface_index, keyboard_endpoint_address if found, or None, None otherwise
    """
    return _find_endpoint(device, PROTOCOL_KEYBOARD, SUBCLASS_BOOT)


def find_gamepad_endpoint(device):
    """
    Try to find a report mouse endpoint in the device and return its
    interface index, and endpoint address.
    :param device: The device to search within
    :return: mouse_interface_index, mouse_endpoint_address if found, or None, None otherwise
    """
    return _find_endpoint(device, PROTOCOL_MOUSE, SUBCLASS_RESERVED, USAGE_GAMEPAD)


def find_joystick_endpoint(device):
    """
    Try to find a report mouse endpoint in the device and return its
    interface index, and endpoint address.
    :param device: The device to search within
    :return: mouse_interface_index, mouse_endpoint_address if found, or None, None otherwise
    """
    return _find_endpoint(device, PROTOCOL_MOUSE, SUBCLASS_RESERVED, USAGE_JOYSTICK)


class AudioFormat:
    """One audio format a USB microphone offers: an alternate setting of an
    audio streaming interface with an isochronous IN endpoint. Its values are
    the arguments of ``usb_host_audio.USBIn``."""

    def __init__(self, interface, alternate):
        self.interface = interface
        """The number of the audio streaming interface"""
        self.alternate = alternate
        """The alternate setting of the interface that streams this format"""
        self.endpoint = None
        """The address of the isochronous IN endpoint the audio arrives on"""
        self.max_packet_size = 0
        """The endpoint's largest packet, in bytes"""
        self.channel_count = 0
        """The number of channels. Stereo samples alternate left, right."""
        self.bits_per_sample = 0
        """The bits of each sample that hold audio"""
        self.bytes_per_sample = 0
        """The bytes each sample occupies in the stream, such as 3 for 24 bit
        samples. ``bytes_per_sample * 8`` is the ``bit_depth`` of ``USBIn``."""
        self.samples_signed = True
        """True when samples are signed. Only the 8 bit PCM8 format is unsigned."""
        self.sample_rates = ()
        """The sample rates offered, in Hz, or empty when `sample_rate_range` is set"""
        self.sample_rate_range = None
        """(lowest, highest) when the microphone takes any rate in a range"""
        self.rate_control = False
        """True when the sample rate is chosen with a SET_CUR request to the endpoint"""
        self._format_tag = 0

    def nearest_rate(self, sample_rate):
        """Return the rate this format offers that is closest to ``sample_rate``."""
        if self.sample_rate_range:
            low, high = self.sample_rate_range
            return min(max(sample_rate, low), high)
        best = 0
        for rate in self.sample_rates:
            if not best or abs(rate - sample_rate) < abs(best - sample_rate):
                best = rate
        return best

    def __repr__(self):
        rates = self.sample_rate_range if self.sample_rate_range else self.sample_rates
        return (
            f"<AudioFormat {self.bits_per_sample} bit x{self.channel_count} {rates} Hz, "
            + f"interface {self.interface} alt {self.alternate}, endpoint 0x{self.endpoint:02x}>"
        )


def _parse_format_type(fmt, desc):
    """Fill in ``fmt`` from a Type I format type descriptor."""
    fmt.channel_count = desc[4]
    fmt.bytes_per_sample = desc[5]
    fmt.bits_per_sample = desc[6]
    count = desc[7]
    # A count of 0 gives a continuous range: the lowest and highest rate.
    rates = []
    for k in range(8, min(8 + 3 * (count or 2), len(desc) - 2), 3):
        rates.append(desc[k] | desc[k + 1] << 8 | desc[k + 2] << 16)
    if count:
        fmt.sample_rates = tuple(rates)
    elif len(rates) == 2:
        fmt.sample_rate_range = tuple(rates)


def parse_microphone_formats(config_descriptor):
    """Return the `AudioFormat` objects of the USB Audio Class 1.0 recording
    interfaces in a configuration descriptor, such as one from
    `get_configuration_descriptor`. USB Audio Class 2.0 interfaces and
    playback (OUT) interfaces are left out.

    :param config_descriptor: The configuration descriptor to search
    :return: A list of `AudioFormat`, empty when there is no microphone
    """
    cfg = config_descriptor
    formats = []
    fmt = None
    i = 0
    while i + 2 <= len(cfg):
        length = cfg[i]
        if length < 2 or i + length > len(cfg):
            break
        descriptor_type = cfg[i + 1]
        if descriptor_type == DESC_INTERFACE:
            fmt = None
            # Alternate setting 0 of a streaming interface has no endpoint.
            if (
                length >= 9
                and cfg[i + 5] == INTERFACE_AUDIO
                and cfg[i + 6] == SUBCLASS_AUDIO_STREAMING
                and cfg[i + 7] != _PROTOCOL_UAC2
                and cfg[i + 3]
            ):
                fmt = AudioFormat(cfg[i + 2], cfg[i + 3])
        elif descriptor_type == _DESC_CS_INTERFACE and fmt is not None:
            subtype = cfg[i + 2]
            if subtype == _AS_GENERAL and length >= 7:
                fmt._format_tag = cfg[i + 5] | cfg[i + 6] << 8
            elif subtype == _AS_FORMAT_TYPE and length >= 8 and cfg[i + 3] == _FORMAT_TYPE_I:
                _parse_format_type(fmt, cfg[i : i + length])
        elif descriptor_type == DESC_ENDPOINT and fmt is not None and length >= 7:
            address = cfg[i + 2]
            # Playback formats have an OUT endpoint instead.
            if address & _DIR_IN and cfg[i + 3] & 3 == _EP_ISOCHRONOUS and fmt.endpoint is None:
                fmt.endpoint = address
                size = cfg[i + 4] | cfg[i + 5] << 8
                fmt.max_packet_size = (size & 0x7FF) * (((size >> 11) & 3) + 1)
                if fmt.channel_count and fmt._format_tag in {_FORMAT_PCM, _FORMAT_PCM8}:
                    fmt.samples_signed = fmt._format_tag != _FORMAT_PCM8
                    formats.append(fmt)
        elif (
            descriptor_type == _DESC_CS_ENDPOINT
            and fmt is not None
            and fmt.endpoint is not None
            and length >= 4
        ):
            fmt.rate_control = bool(cfg[i + 3] & _EP_SAMPLING_FREQ_CONTROL)
        i += length
    return formats


def find_microphone_formats(device):
    """Return the audio formats a USB microphone offers. Many webcams and USB
    audio adapters have a microphone too.

    :param device: The device to search within
    :return: A list of `AudioFormat`, empty when the device has no microphone
    """
    return parse_microphone_formats(get_configuration_descriptor(device, 0))


def find_microphone():
    """Return the first attached device that has a USB Audio Class 1.0
    microphone, or None. Other devices, such as keyboards and mice, are skipped.

    Webcam configuration descriptors are several KB long. A device whose
    descriptor doesn't fit the firmware's enumeration buffer is never mounted,
    so it is not found.

    :return: A ``usb.core.Device``, or None
    """
    for device in usb.core.find(find_all=True):
        try:
            if find_microphone_formats(device):
                return device
        except usb.core.USBError:
            continue  # Could not read its descriptor, so it is not one to use.
    return None


def choose_microphone_format(formats, sample_rate=16000, bit_depth=16, channel_count=1):
    """Return the format closest to the request: the bit depth matters most,
    then the channel count, then the sample rate. Use the format's
    `AudioFormat.nearest_rate` for the sample rate to set.

    :param formats: The `AudioFormat` objects to choose from, such as the ones
      `find_microphone_formats` returns
    :param int sample_rate: The sample rate wanted, in Hz
    :param int bit_depth: The bits per sample wanted
    :param int channel_count: The number of channels wanted
    :return: An `AudioFormat`, or None when ``formats`` is empty
    """
    best = None
    best_score = None
    for fmt in formats:
        score = (
            abs(fmt.bits_per_sample - bit_depth),
            abs(fmt.channel_count - channel_count),
            abs(fmt.nearest_rate(sample_rate) - sample_rate),
        )
        if best is None or score < best_score:
            best = fmt
            best_score = score
    return best
