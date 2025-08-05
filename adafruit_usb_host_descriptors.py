# SPDX-FileCopyrightText: 2017 Scott Shawcroft, written for Adafruit Industries
# SPDX-FileCopyrightText: Copyright (c) 2023 Scott Shawcroft for Adafruit Industries
# SPDX-FileCopyrightText: Copyright (c) 2025 Anne Barela for Adafruit Industries
#
# SPDX-License-Identifier: MIT

"""
`adafruit_usb_host_descriptors`
================================================================================

"""

import usb.core

# imports

__version__ = "0.0.0+auto.0"
__repo__ = "https://github.com/adafruit/Adafruit_CircuitPython_USB_Host_Descriptors.git"

# USB Descriptor Type constants
DESC_DEVICE = 1
DESC_CONFIGURATION = 2
DESC_STRING = 3
DESC_INTERFACE = 4
DESC_ENDPOINT = 5
DESC_DEVICE_QUALIFIER = 6
DESC_OTHER_SPEED_CONFIGURATION = 7
DESC_INTERFACE_POWER = 8
DESC_OTG = 9
DESC_DEBUG = 10
DESC_INTERFACE_ASSOCIATION = 11

# USB Class codes
CLASS_PER_INTERFACE = 0x00
CLASS_AUDIO = 0x01
CLASS_COMM = 0x02
CLASS_HID = 0x03
CLASS_PHYSICAL = 0x05
CLASS_IMAGE = 0x06
CLASS_PRINTER = 0x07
CLASS_MASS_STORAGE = 0x08
CLASS_HUB = 0x09
CLASS_DATA = 0x0A
CLASS_SMART_CARD = 0x0B
CLASS_CONTENT_SECURITY = 0x0D
CLASS_VIDEO = 0x0E
CLASS_PERSONAL_HEALTHCARE = 0x0F
CLASS_DIAGNOSTIC_DEVICE = 0xDC
CLASS_WIRELESS = 0xE0
CLASS_APPLICATION = 0xFE
CLASS_VENDOR_SPECIFIC = 0xFF

# Direction constants
DIR_OUT = 0x00
DIR_IN = 0x80


def get_descriptor(device, desc_type, index, buf, language_id=0):
    """Fetch the descriptor from the device into buf."""
    return device.ctrl_transfer(
        DIR_IN | 0x00,  # bmRequestType
        6,  # bRequest (GET_DESCRIPTOR)
        (desc_type << 8) | index,  # wValue
        language_id,  # wIndex
        buf,  # data_or_wLength
    )


def get_device_descriptor(device):
    """Fetch the device descriptor and return it."""
    buf = bytearray(18)  # Device descriptor is always 18 bytes
    length = get_descriptor(device, DESC_DEVICE, 0, buf)
    if length != 18:
        raise ValueError("Invalid device descriptor length")
    return buf


def get_configuration_descriptor(device, index):
    """Fetch the configuration descriptor, its associated descriptors and return it."""
    # First get just the configuration descriptor to know the total length
    buf = bytearray(9)  # Configuration descriptor is 9 bytes
    length = get_descriptor(device, DESC_CONFIGURATION, index, buf)
    if length < 9:
        raise ValueError("Invalid configuration descriptor length")

    # Extract the total length from the descriptor
    total_length = (buf[3] << 8) | buf[2]

    # Now get the full descriptor including all associated descriptors
    full_buf = bytearray(total_length)
    length = get_descriptor(device, DESC_CONFIGURATION, index, full_buf)
    if length != total_length:
        raise ValueError("Configuration descriptor length mismatch")

    return full_buf


def find_boot_mouse_endpoint(device):
    """Try to find a boot mouse endpoint in the device and return its interface
       index, and endpoint address.

    :param device: The device to search within
    :return: mouse_interface_index, mouse_endpoint_address if found,
             or None, None otherwise
    """
    config_descriptor = get_configuration_descriptor(device, 0)

    i = 0
    current_interface = None
    while i < len(config_descriptor):
        descriptor_len = config_descriptor[i]
        descriptor_type = config_descriptor[i + 1]

        if descriptor_type == DESC_INTERFACE:
            interface_number = config_descriptor[i + 2]
            interface_class = config_descriptor[i + 5]
            interface_subclass = config_descriptor[i + 6]
            interface_protocol = config_descriptor[i + 7]

            # Check for HID boot mouse interface
            if (interface_class == CLASS_HID and
                interface_subclass == 1 and  # Boot Interface Subclass
                    interface_protocol == 2):    # Mouse Protocol
                current_interface = interface_number
            else:
                current_interface = None

        elif descriptor_type == DESC_ENDPOINT and current_interface is not None:
            endpoint_address = config_descriptor[i + 2]
            if endpoint_address & DIR_IN:  # Input endpoint
                return current_interface, endpoint_address

        i += descriptor_len

    return None, None

# ============================================================================
# ENHANCED HID DEVICE DETECTION EXTENSIONS
# ============================================================================
# The following functions extend the original adafruit_usb_host_descriptors
# library with comprehensive HID device detection and management capabilities
# specifically designed for USB host boards like the Adafruit Fruit Jam.
#
# Features:
# - Multi-device detection (keyboards, mice, gamepads)
# - Composite device support (keyboard+trackpad combos)
# - Device caching
# - Real-time device change monitoring
# - Device classification
#
# ============================================================================

# Constants for HID device identification
HID_CLASS = 0x03
BOOT_SUBCLASS = 0x01
KEYBOARD_PROTOCOL = 0x01
MOUSE_PROTOCOL = 0x02
NO_PROTOCOL = 0x00

# Enhanced device cache with composite device support
_device_cache = {
    'keyboards': [],
    'mice': [],
    'gamepads': [],
    'composite_devices': {},  # Track devices with multiple HID interfaces
    'last_scan': None
}

# Configuration
_cache_timeout = 1.0  # Default 1 second cache timeout
_device_change_callbacks = []

# Device filtering support
_device_filters = {
    'allowed_vids': None,
    'blocked_vids': set(),
    'allowed_manufacturers': None,
    'blocked_manufacturers': set()
}

def set_cache_timeout(timeout_seconds):
    """
    Set the device cache timeout.

    @param timeout_seconds: Cache timeout in seconds (0 disables caching)
    @type timeout_seconds: float
    """
    global _cache_timeout
    _cache_timeout = max(0.0, timeout_seconds)

def register_device_change_callback(callback):
    """
    Register a callback to be called when devices are added/removed.

    @param callback: Function called with (device_type, action, index) parameters
    @type callback: callable

    @par Example:
    @code
    def on_device_change(device_type, action, index):
        print(f"Device {action}: {device_type}[{index}]")

    register_device_change_callback(on_device_change)
    @endcode
    """
    if callback not in _device_change_callbacks:
        _device_change_callbacks.append(callback)

def set_device_filter(allowed_vids=None, blocked_vids=None,
                      allowed_manufacturers=None, blocked_manufacturers=None):
    """
    Set device filters to limit which devices are detected.

    @param allowed_vids: Set of allowed vendor IDs (None = allow all)
    @param blocked_vids: Set of blocked vendor IDs
    @param allowed_manufacturers: Set of allowed manufacturer names (lowercase)
    @param blocked_manufacturers: Set of blocked manufacturer names (lowercase)

    @par Example:
    @code
    # Only detect Logitech devices
    set_device_filter(allowed_vids={0x046D})

    # Block specific problematic devices
    set_device_filter(blocked_vids={0x1234, 0x5678})
    @endcode
    """
    global _device_filters
    if allowed_vids is not None:
        _device_filters['allowed_vids'] = set(allowed_vids)
    if blocked_vids is not None:
        _device_filters['blocked_vids'] = set(blocked_vids)
    if allowed_manufacturers is not None:
        _device_filters['allowed_manufacturers'] = \
            set(m.lower() for m in allowed_manufacturers)
    if blocked_manufacturers is not None:
        _device_filters['blocked_manufacturers'] = \
            set(m.lower() for m in blocked_manufacturers)

def _device_passes_filter(device_info):
    """Check if device passes current filters"""
    vid = device_info['vid']
    manufacturer = device_info.get('manufacturer', '').lower()

    # Check VID filters
    if _device_filters['allowed_vids'] and vid not in _device_filters['allowed_vids']:
        return False
    if vid in _device_filters['blocked_vids']:
        return False

    # Check manufacturer filters
    if (_device_filters['allowed_manufacturers'] and
            manufacturer not in _device_filters['allowed_manufacturers']):
        return False
    if manufacturer in _device_filters['blocked_manufacturers']:
        return False

    return True

def _notify_device_changes(old_cache, new_cache):
    """Notify callbacks of device changes"""
    for device_type in ['keyboards', 'mice', 'gamepads']:
        old_count = len(old_cache.get(device_type, []))
        new_count = len(new_cache.get(device_type, []))

        if new_count > old_count:
            # Device added
            for callback in _device_change_callbacks:
                try:
                    # Remove 's' from plural
                    callback(device_type[:-1], 'added', new_count - 1)
                except Exception as e:
                    print(f"Callback error: {e}")
        elif new_count < old_count:
            # Device removed
            for callback in _device_change_callbacks:
                try:
                    callback(device_type[:-1], 'removed', old_count - 1)
                except Exception as e:
                    print(f"Callback error: {e}")

def _refresh_device_cache(force_refresh=False):
    """
    Refresh the internal device cache by scanning all USB devices.

    @param force_refresh: Force a refresh even if recently scanned
    @type force_refresh: bool
    @raises usb.core.USBError: If USB scanning fails
    @raises ImportError: If time module is not available
    """
    import time

    # Only refresh if forced or cache is empty/old
    current_time = time.monotonic()
    if not force_refresh and _device_cache['last_scan'] is not None:
        if _cache_timeout > 0 and current_time - _device_cache['last_scan'] \
                < _cache_timeout:
            return

    # Store old cache for change detection
    old_cache = {
        'keyboards': _device_cache['keyboards'].copy(),
        'mice': _device_cache['mice'].copy(),
        'gamepads': _device_cache['gamepads'].copy()
    }

    # Clear cache
    _device_cache['keyboards'].clear()
    _device_cache['mice'].clear()
    _device_cache['gamepads'].clear()
    _device_cache['composite_devices'].clear()

    # Scan all connected USB devices
    try:
        for device in usb.core.find(find_all=True):
            _analyze_device(device)
    except usb.core.USBError as e:
        print(f"USB error scanning devices: {e}")
    except usb.core.NoBackendError as e:
        print(f"USB backend error: {e}")

    _device_cache['last_scan'] = current_time

    # Notify callbacks of changes
    if _device_change_callbacks:
        _notify_device_changes(old_cache, _device_cache)

def _analyze_device(device):
    """
    Analyze a USB device to determine if it's a keyboard, mouse, or gamepad.
    Properly handles composite devices with multiple HID interfaces.

    @param device: USB device object from usb.core.find()
    @type device: usb.core.Device
    @raises usb.core.USBError: If device descriptor cannot be read
    @raises IndexError: If descriptor parsing encounters invalid data
    @raises AttributeError: If device lacks expected attributes
    """
    try:
        # Get configuration descriptor
        config_descriptor = get_configuration_descriptor(device, 0)

        # Collect all HID interfaces for this device
        hid_interfaces = []

        # Parse descriptor to find HID interfaces
        i = 0
        while i < len(config_descriptor):
            descriptor_len = config_descriptor[i]
            descriptor_type = config_descriptor[i + 1]

            if descriptor_type == DESC_INTERFACE:
                interface_number = config_descriptor[i + 2]
                interface_class = config_descriptor[i + 5]
                interface_subclass = config_descriptor[i + 6]
                interface_protocol = config_descriptor[i + 7]

                # Check if this is an HID interface
                if interface_class == HID_CLASS:
                    # Find the corresponding input endpoint
                    endpoint_address = _find_input_endpoint(config_descriptor,
                                                            i + descriptor_len)

                    if endpoint_address is not None:
                        interface_info = {
                            'device': device,
                            'interface_index': interface_number,
                            'endpoint_address': endpoint_address,
                            'interface_class': interface_class,
                            'interface_subclass': interface_subclass,
                            'interface_protocol': interface_protocol,
                            'vid': device.idVendor,
                            'pid': device.idProduct,
                            'manufacturer': getattr(device, 'manufacturer', 'Unknown'),
                            'product': getattr(device, 'product', 'Unknown')
                        }

                        # Apply device filters
                        if _device_passes_filter(interface_info):
                            hid_interfaces.append(interface_info)

            i += descriptor_len

        # Process all HID interfaces for this device
        if hid_interfaces:
            device_id = f"{device.idVendor:04x}:{device.idProduct:04x}:\
                            {getattr(device, 'serial_number', 'no_serial')}"
            interfaces_by_type = {}

            # Classify each interface individually
            for interface_info in hid_interfaces:
                interface_type = _classify_hid_device(interface_info)
                if interface_type not in interfaces_by_type:
                    interfaces_by_type[interface_type] = []
                interfaces_by_type[interface_type].append(interface_info)

            # Store device in ALL applicable categories
            for device_type, interfaces in interfaces_by_type.items():
                # For each type, select the best interface (boot protocol preferred)
                best_interface = _select_best_interface_for_type(interfaces,
                                                                 device_type)

                if device_type == 'keyboard' and not _device_already_cached(device,
                                                                            'keyboards'
                                                                            ):
                    _device_cache['keyboards'].append(best_interface)
                elif device_type == 'mouse' and not _device_already_cached(device,
                                                                           'mice'):
                    _device_cache['mice'].append(best_interface)
                elif device_type == 'gamepad' and not _device_already_cached(device,
                                                                             'gamepads'
                                                                             ):
                    _device_cache['gamepads'].append(best_interface)

            # Track composite devices for reference
            if len(interfaces_by_type) > 1:
                _device_cache['composite_devices'][device_id] = {
                    'device': device,
                    'interfaces_by_type': interfaces_by_type,
                    'product': getattr(device, 'product', 'Unknown'),
                    'types': list(interfaces_by_type.keys())
                }

    except usb.core.USBError as e:
        # Silently ignore USB errors for devices we can't access
        pass
    except IndexError as e:
        print(f"Descriptor parsing error for device {device}: {e}")
    except AttributeError as e:
        print(f"Device attribute error for device {device}: {e}")

def _select_best_interface_for_type(interfaces, device_type):
    """
    Select the best interface for a specific device type.
    Prefers boot protocol interfaces when available.
    """
    boot_interfaces = [iface for iface in interfaces
                       if iface['interface_subclass'] == BOOT_SUBCLASS]

    if boot_interfaces:
        # Prefer boot protocol interfaces
        for iface in boot_interfaces:
            expected_protocol = {
                'keyboard': KEYBOARD_PROTOCOL,
                'mouse': MOUSE_PROTOCOL
            }.get(device_type, NO_PROTOCOL)

            if iface['interface_protocol'] == expected_protocol:
                return iface
        return boot_interfaces[0]  # Any boot interface is better than non-boot

    return interfaces[0]  # Fallback to first interface

def _device_already_cached(device, device_type):
    """
    Check if a device is already in the cache to avoid duplicates.

    @param device: USB device object
    @type device: usb.core.Device
    @param device_type: Type of device cache to check ('keyboards', 'mice', 'gamepads')
    @type device_type: str
    @return: True if device already cached, False otherwise
    @rtype: bool
    """
    try:
        for cached_device_info in _device_cache[device_type]:
            cached_device = cached_device_info['device']
            if (cached_device.idVendor == device.idVendor and
                cached_device.idProduct == device.idProduct and
                getattr(cached_device, 'serial_number', None) ==
                    getattr(device, 'serial_number', None)):
                return True
    except (KeyError, AttributeError):
        pass
    return False

def _find_input_endpoint(config_descriptor, start_index):
    """
    Find the input endpoint address for an HID interface.

    @param config_descriptor: Configuration descriptor bytes
    @type config_descriptor: bytes
    @param start_index: Index to start searching from
    @type start_index: int
    @return: Endpoint address or None if not found
    @rtype: int or None
    @raises IndexError: If descriptor indices are out of bounds
    """
    try:
        i = start_index
        while i < len(config_descriptor):
            descriptor_len = config_descriptor[i]
            descriptor_type = config_descriptor[i + 1]

            if descriptor_type == DESC_ENDPOINT:
                endpoint_address = config_descriptor[i + 2]
                # Return first input endpoint found
                if endpoint_address & DIR_IN:
                    return endpoint_address
            elif descriptor_type == DESC_INTERFACE:
                # Reached next interface, stop searching
                break

            i += descriptor_len

    except IndexError as e:
        print(f"Index error finding endpoint: {e}")

    return None

def _classify_hid_device(device_info):
    """
    Classify an HID device as keyboard, mouse, or gamepad.

    @param device_info: Dictionary with device information
    @type device_info: dict
    @return: Device type classification
    @rtype: str
    @retval 'keyboard': Device is classified as a keyboard
    @retval 'mouse': Device is classified as a mouse
    @retval 'gamepad': Device is classified as a gamepad
    @retval 'unknown': Device type could not be determined
    """
    protocol = device_info['interface_protocol']
    subclass = device_info['interface_subclass']
    vid = device_info['vid']
    pid = device_info['pid']
    product = device_info['product'].lower() if device_info['product'] else ''

    # Boot protocol devices are easy to identify
    if subclass == BOOT_SUBCLASS:
        if protocol == KEYBOARD_PROTOCOL:
            return 'keyboard'
        elif protocol == MOUSE_PROTOCOL:
            return 'mouse'

    # For non-boot HID devices, use heuristics
    # Check product name for common keywords
    keyboard_keywords = ['keyboard', 'kbd', 'keypad']
    mouse_keywords = ['mouse', 'pointer', 'trackball', 'touchpad', 'trackpad']
    gamepad_keywords = ['gamepad', 'controller', 'joystick', 'xbox', 'playstation',
                        'ps3', 'ps4', 'ps5']

    product_lower = product.lower()

    for keyword in keyboard_keywords:
        if keyword in product_lower:
            return 'keyboard'

    for keyword in mouse_keywords:
        if keyword in product_lower:
            return 'mouse'

    for keyword in gamepad_keywords:
        if keyword in product_lower:
            return 'gamepad'

    # Check known VID/PID combinations for common devices
    known_keyboards = [
        (0x046D, 0xC52B),  # Logitech keyboards
        (0x413C, 0x2113),  # Dell keyboards
        (0x045E, 0x0750),  # Microsoft keyboards
    ]

    known_mice = [
        (0x046D, 0xC077),  # Logitech mice
        (0x1532, 0x0037),  # Razer mice
        (0x045E, 0x0040),  # Microsoft mice
    ]

    known_gamepads = [
        (0x045E, 0x028E),  # Xbox 360 Controller
        (0x045E, 0x02D1),  # Xbox One Controller
        (0x054C, 0x0268),  # PS3 Controller
        (0x054C, 0x05C4),  # PS4 Controller
        (0x054C, 0x0CE6),  # PS5 Controller
    ]

    if (vid, pid) in known_keyboards:
        return 'keyboard'
    elif (vid, pid) in known_mice:
        return 'mouse'
    elif (vid, pid) in known_gamepads:
        return 'gamepad'

    # Default: if it's not boot protocol and we can't identify it,
    # assume it's a gamepad (most non-boot HID devices are)
    return 'gamepad'

# ============================================================================
# PUBLIC API FUNCTIONS
# ============================================================================

def count_keyboards(refresh=False):
    """
    Count the number of keyboards connected to USB host ports.

    This function scans all connected USB devices and counts those identified
    as keyboards using boot protocol detection and device classification heuristics.

    @param refresh: Force a device scan refresh instead of using cached results
    @type refresh: bool
    @return: Number of keyboards detected
    @rtype: int
    @retval 0: No keyboards detected
    @retval 1+: Number of keyboards detected
    @raises usb.core.USBError: If USB device scanning fails

    @par Example:
    @code
    num_keyboards = count_keyboards()
    if num_keyboards > 0:
        print(f"Found {num_keyboards} keyboard(s)")
    @endcode
    """
    _refresh_device_cache(refresh)
    return len(_device_cache['keyboards'])

def count_mice(refresh=False):
    """
    Count the number of mice connected to USB host ports.

    This function scans all connected USB devices and counts those identified
    as mice using boot protocol detection and device classification heuristics.
    Includes trackpads from composite keyboard+trackpad devices.

    @param refresh: Force a device scan refresh instead of using cached results
    @type refresh: bool
    @return: Number of mice detected
    @rtype: int
    @retval 0: No mice detected
    @retval 1+: Number of mice detected
    @raises usb.core.USBError: If USB device scanning fails

    @par Example:
    @code
    num_mice = count_mice()
    if num_mice > 0:
        print(f"Found {num_mice} mouse/mice")
    @endcode
    """
    _refresh_device_cache(refresh)
    return len(_device_cache['mice'])

def count_gamepads(refresh=False):
    """
    Count the number of gamepads connected to USB host ports.

    This function scans all connected USB devices and counts those identified
    as gamepads including Xbox controllers, PlayStation controllers, and generic
    USB game controllers.

    @param refresh: Force a device scan refresh instead of using cached results
    @type refresh: bool
    @return: Number of gamepads detected
    @rtype: int
    @retval 0: No gamepads detected
    @retval 1+: Number of gamepads detected
    @raises usb.core.USBError: If USB device scanning fails

    @par Example:
    @code
    num_gamepads = count_gamepads()
    if num_gamepads > 0:
        print(f"Found {num_gamepads} gamepad(s)")
    @endcode
    """
    _refresh_device_cache(refresh)
    return len(_device_cache['gamepads'])

def get_keyboard_info(index):
    """
    Get interface index and endpoint address for a keyboard.

    Returns the USB interface index and input endpoint address needed to
    communicate with the specified keyboard. This information is required
    for reading input reports from the keyboard.

    @param index: Keyboard index (0 for first keyboard, 1 for second, etc.)
    @type index: int
    @return: Tuple of (interface_index, endpoint_address) or (None, None) if not found
    @rtype: tuple[int, int] or tuple[None, None]
    @raises IndexError: If index is negative
    @raises usb.core.USBError: If device information cannot be retrieved

    @par Example:
    @code
    interface_index, endpoint_address = get_keyboard_info(0)  # First keyboard
    if interface_index is not None:
        print(f"Keyboard interface:
                {interface_index}, endpoint: 0x{endpoint_address:02x}")
    @endcode
    """
    if index < 0:
        raise IndexError("Device index cannot be negative")

    _refresh_device_cache()

    try:
        if index < len(_device_cache['keyboards']):
            device_info = _device_cache['keyboards'][index]
            return device_info['interface_index'], device_info['endpoint_address']
    except (IndexError, KeyError) as e:
        print(f"Error accessing keyboard info: {e}")

    return None, None

def get_mouse_info(index):
    """
    Get interface index and endpoint address for a mouse.

    Returns the USB interface index and input endpoint address needed to
    communicate with the specified mouse. This information is required
    for reading input reports from the mouse.

    @param index: Mouse index (0 for first mouse, 1 for second, etc.)
    @type index: int
    @return: Tuple of (interface_index, endpoint_address) or (None, None) if not found
    @rtype: tuple[int, int] or tuple[None, None]
    @raises IndexError: If index is negative
    @raises usb.core.USBError: If device information cannot be retrieved

    @par Example:
    @code
    interface_index, endpoint_address = get_mouse_info(0)  # First mouse
    if interface_index is not None:
        print(f"Mouse interface: {interface_index}, endpoint: 0x{endpoint_address:02x}")
    @endcode
    """
    if index < 0:
        raise IndexError("Device index cannot be negative")

    _refresh_device_cache()

    try:
        if index < len(_device_cache['mice']):
            device_info = _device_cache['mice'][index]
            return device_info['interface_index'], device_info['endpoint_address']
    except (IndexError, KeyError) as e:
        print(f"Error accessing mouse info: {e}")

    return None, None

def get_gamepad_info(index):
    """
    Get interface index and endpoint address for a gamepad.

    Returns the USB interface index and input endpoint address needed to
    communicate with the specified gamepad. This information is required
    for reading input reports from the gamepad.

    @param index: Gamepad index (0 for first gamepad, 1 for second, etc.)
    @type index: int
    @return: Tuple of (interface_index, endpoint_address) or (None, None) if not found
    @rtype: tuple[int, int] or tuple[None, None]
    @raises IndexError: If index is negative
    @raises usb.core.USBError: If device information cannot be retrieved

    @par Example:
    @code
    interface_index, endpoint_address = get_gamepad_info(0)  # First gamepad
    if interface_index is not None:
        print(f"Gamepad interface: {interface_index},
                endpoint: 0x{endpoint_address:02x}")
    @endcode
    """
    if index < 0:
        raise IndexError("Device index cannot be negative")

    _refresh_device_cache()

    try:
        if index < len(_device_cache['gamepads']):
            device_info = _device_cache['gamepads'][index]
            return device_info['interface_index'], device_info['endpoint_address']
    except (IndexError, KeyError) as e:
        print(f"Error accessing gamepad info: {e}")

    return None, None

def get_keyboard_device(index):
    """
    Get the USB device object for a keyboard.

    Returns the underlying USB device object that can be used for direct
    communication with the keyboard using PyUSB functions.

    @param index: Keyboard index (0 for first keyboard, 1 for second, etc.)
    @type index: int
    @return: USB device object or None if not found
    @rtype: usb.core.Device or None
    @raises IndexError: If index is negative
    @raises usb.core.USBError: If device information cannot be retrieved

    @par Example:
    @code
    device = get_keyboard_device(0)
    if device:
        print(f"Keyboard VID:PID = {device.idVendor:04x}:{device.idProduct:04x}")
        print(f"Manufacturer: {device.manufacturer}")
        print(f"Product: {device.product}")
    @endcode
    """
    if index < 0:
        raise IndexError("Device index cannot be negative")

    _refresh_device_cache()

    try:
        if index < len(_device_cache['keyboards']):
            return _device_cache['keyboards'][index]['device']
    except (IndexError, KeyError) as e:
        print(f"Error accessing keyboard device: {e}")

    return None

def get_mouse_device(index):
    """
    Get the USB device object for a mouse.

    Returns the underlying USB device object that can be used for direct
    communication with the mouse using PyUSB functions.

    @param index: Mouse index (0 for first mouse, 1 for second, etc.)
    @type index: int
    @return: USB device object or None if not found
    @rtype: usb.core.Device or None
    @raises IndexError: If index is negative
    @raises usb.core.USBError: If device information cannot be retrieved

    @par Example:
    @code
    device = get_mouse_device(0)
    if device:
        print(f"Mouse VID:PID = {device.idVendor:04x}:{device.idProduct:04x}")
        print(f"Manufacturer: {device.manufacturer}")
        print(f"Product: {device.product}")
    @endcode
    """
    if index < 0:
        raise IndexError("Device index cannot be negative")

    _refresh_device_cache()

    try:
        if index < len(_device_cache['mice']):
            return _device_cache['mice'][index]['device']
    except (IndexError, KeyError) as e:
        print(f"Error accessing mouse device: {e}")

    return None

def get_gamepad_device(index):
    """
    Get the USB device object for a gamepad.

    Returns the underlying USB device object that can be used for direct
    communication with the gamepad using PyUSB functions.

    @param index: Gamepad index (0 for first gamepad, 1 for second, etc.)
    @type index: int
    @return: USB device object or None if not found
    @rtype: usb.core.Device or None
    @raises IndexError: If index is negative
    @raises usb.core.USBError: If device information cannot be retrieved

    @par Example:
    @code
    device = get_gamepad_device(0)
    if device:
        print(f"Gamepad VID:PID = {device.idVendor:04x}:{device.idProduct:04x}")
        print(f"Manufacturer: {device.manufacturer}")
        print(f"Product: {device.product}")
    @endcode
    """
    if index < 0:
        raise IndexError("Device index cannot be negative")

    _refresh_device_cache()

    try:
        if index < len(_device_cache['gamepads']):
            return _device_cache['gamepads'][index]['device']
    except (IndexError, KeyError) as e:
        print(f"Error accessing gamepad device: {e}")

    return None

def list_all_hid_devices():
    """
    Get a comprehensive summary of all detected HID devices.

    Returns a dictionary containing counts and detailed information for all
    keyboards, mice, and gamepads detected on the USB host ports.

    @return: Summary dictionary with device counts and lists
    @rtype: dict
    @raises usb.core.USBError: If USB device scanning fails

    @par Return Dictionary Structure:
    @code
    {
        'keyboards': {
            'count': int,
            'devices': [
                {
                    'index': int,
                    'vid': int,
                    'pid': int,
                    'manufacturer': str,
                    'product': str,
                    'interface_index': int,
                    'endpoint_address': int
                },
                ...
            ]
        },
        'mice': { ... },
        'gamepads': { ... }
    }
    @endcode

    @par Example:
    @code
    summary = list_all_hid_devices()
    print(f"Found {summary['keyboards']['count']} keyboards")
    print(f"Found {summary['mice']['count']} mice")
    print(f"Found {summary['gamepads']['count']} gamepads")

    for device in summary['keyboards']['devices']:
        print(f"Keyboard[{device['index']}]: {device['manufacturer']}
                {device['product']}")
    @endcode
    """
    _refresh_device_cache(force_refresh=True)

    try:
        return {
            'keyboards': {
                'count': len(_device_cache['keyboards']),
                'devices': [
                    {
                        'index': i,
                        'vid': dev['vid'],
                        'pid': dev['pid'],
                        'manufacturer': dev['manufacturer'],
                        'product': dev['product'],
                        'interface_index': dev['interface_index'],
                        'endpoint_address': dev['endpoint_address']
                    }
                    for i, dev in enumerate(_device_cache['keyboards'])
                ]
            },
            'mice': {
                'count': len(_device_cache['mice']),
                'devices': [
                    {
                        'index': i,
                        'vid': dev['vid'],
                        'pid': dev['pid'],
                        'manufacturer': dev['manufacturer'],
                        'product': dev['product'],
                        'interface_index': dev['interface_index'],
                        'endpoint_address': dev['endpoint_address']
                    }
                    for i, dev in enumerate(_device_cache['mice'])
                ]
            },
            'gamepads': {
                'count': len(_device_cache['gamepads']),
                'devices': [
                    {
                        'index': i,
                        'vid': dev['vid'],
                        'pid': dev['pid'],
                        'manufacturer': dev['manufacturer'],
                        'product': dev['product'],
                        'interface_index': dev['interface_index'],
                        'endpoint_address': dev['endpoint_address']
                    }
                    for i, dev in enumerate(_device_cache['gamepads'])
                ]
            }
        }
    except KeyError as e:
        print(f"Error building device summary: {e}")
        return {'keyboards': {'count': 0, 'devices': []},
                'mice': {'count': 0, 'devices': []},
                'gamepads': {'count': 0, 'devices': []}}

def get_composite_device_info():
    """
    Get information about composite devices (devices with multiple HID interfaces).

    @return: Dictionary of composite devices
    @rtype: dict

    @par Example:
    @code
    composite_devices = get_composite_device_info()
    for device_id, info in composite_devices.items():
        print(f"Composite device: {info['product']}")
        print(f"  Types: {', '.join(info['types'])}")
    @endcode
    """
    _refresh_device_cache()
    return _device_cache['composite_devices'].copy()

def is_composite_device(device_type, index):
    """
    Check if a device at given index is part of a composite device.

    @param device_type: 'keyboard', 'mouse', or 'gamepad'
    @param index: Device index
    @return: Tuple of (is_composite, other_types)
    @rtype: tuple[bool, list]

    @par Example:
    @code
    is_composite, other_types = is_composite_device('keyboard', 0)
    if is_composite:
        print(f"Keyboard also has: {other_types}")
    @endcode
    """
    try:
        if device_type == 'keyboard':
            device = get_keyboard_device(index)
        elif device_type == 'mouse':
            device = get_mouse_device(index)
        elif device_type == 'gamepad':
            device = get_gamepad_device(index)
        else:
            return False, []

        if device is None:
            return False, []

        device_id = f"{device.idVendor:04x}:{device.idProduct:04x}: \
                      {getattr(device, 'serial_number', 'no_serial')}"

        if device_id in _device_cache['composite_devices']:
            composite_info = _device_cache['composite_devices'][device_id]
            other_types = [t for t in composite_info['types'] if t != device_type]
            return True, other_types

        return False, []

    except Exception:
        return False, []

def get_companion_interfaces(device_type, index):
    """
    Get companion interfaces for a composite device.
    For example, if you have a keyboard+trackpad, calling this with
    ('keyboard', 0) will return the mouse interface info.

    @param device_type: Current device type ('keyboard', 'mouse', or 'gamepad')
    @param index: Device index
    @return: Dictionary mapping companion types to their interface info
    @rtype: dict

    @par Example:
    @code
    companions = get_companion_interfaces('keyboard', 0)
    if 'mouse' in companions:
        print("This keyboard has a trackpad!")
        trackpad_info = companions['mouse']
        print(f"Trackpad interface: {trackpad_info['interface_index']}")
    @endcode
    """
    try:
        # Get the device
        if device_type == 'keyboard':
            device = get_keyboard_device(index)
        elif device_type == 'mouse':
            device = get_mouse_device(index)
        elif device_type == 'gamepad':
            device = get_gamepad_device(index)
        else:
            return {}

        if device is None:
            return {}

        device_id = f"{device.idVendor:04x}:{device.idProduct:04x}: \
                      {getattr(device, 'serial_number', 'no_serial')}"

        if device_id in _device_cache['composite_devices']:
            composite_info = _device_cache['composite_devices'][device_id]
            companions = {}

            for companion_type, interfaces in \
                    composite_info['interfaces_by_type'].items():
                if companion_type != device_type:
                    best_interface = _select_best_interface_for_type(interfaces,
                                                                     companion_type)
                    companions[companion_type] = {
                        'interface_index': best_interface['interface_index'],
                        'endpoint_address': best_interface['endpoint_address'],
                        'interface_info': best_interface
                    }

            return companions

        return {}

    except Exception as e:
        print(f"Error getting companion interfaces: {e}")
        return {}

def force_refresh():
    """
    Force a complete refresh of the device cache.

    Forces an immediate rescan of all connected USB devices, bypassing the
    normal cache timeout. Call this when you know devices have been connected
    or disconnected and need immediate updated results.

    @raises usb.core.USBError: If USB device scanning fails
    @raises usb.core.NoBackendError: If USB backend is not available

    @par Example:
    @code
    # Connect a new keyboard, then force refresh
    force_refresh()
    keyboards = count_keyboards()  # Will reflect newly connected device
    @endcode
    """
    _refresh_device_cache(force_refresh=True)

def is_device_connected(device_type, index):
    """
    Check if a device is still connected and responding.

    @param device_type: 'keyboard', 'mouse', or 'gamepad'
    @param index: Device index
    @return: True if device is connected and responding
    @rtype: bool

    @par Example:
    @code
    if is_device_connected('keyboard', 0):
        print("Keyboard is still connected")
    else:
        print("Keyboard has been disconnected")
    @endcode
    """
    try:
        device = None
        if device_type == 'keyboard':
            device = get_keyboard_device(index)
        elif device_type == 'mouse':
            device = get_mouse_device(index)
        elif device_type == 'gamepad':
            device = get_gamepad_device(index)

        if device is None:
            return False

        # Try to read device descriptor to verify connectivity
        try:
            desc = get_device_descriptor(device)
            return len(desc) == 18
        except usb.core.USBError:
            return False

    except Exception:
        return False

# Convenience function for generic access
def get_info(device_type, index):
    """
    Generic function to get interface_index and endpoint_address for any device type.

    This is a convenience function that wraps the specific device info functions
    and provides a unified interface for getting device communication parameters.

    @param device_type: Type of device to query
    @type device_type: str
    @param index: Device index (0, 1, etc.)
    @type index: int
    @return: Tuple of (interface_index, endpoint_address) or (None, None)
    @rtype: tuple[int, int] or tuple[None, None]
    @raises ValueError: If device_type is not valid
    @raises IndexError: If index is negative
    @raises usb.core.USBError: If device information cannot be retrieved

    @par Valid device_type values:
    - 'keyboard': Query keyboard devices
    - 'mouse': Query mouse devices
    - 'gamepad': Query gamepad devices

    @par Example:
    @code
    interface_index, endpoint_address = get_info('keyboard', 0)
    interface_index, endpoint_address = get_info('mouse', 1)
    interface_index, endpoint_address = get_info('gamepad', 0)
    @endcode
    """
    if device_type == 'keyboard':
        return get_keyboard_info(index)
    elif device_type == 'mouse':
        return get_mouse_info(index)
    elif device_type == 'gamepad':
        return get_gamepad_info(index)
    else:
        raise ValueError(f"Invalid device_type: {device_type}. Must be 'keyboard', \
                          'mouse', or 'gamepad'")
