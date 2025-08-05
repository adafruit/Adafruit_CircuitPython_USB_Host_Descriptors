# SPDX-FileCopyrightText: Copyright (c) 2025 Anne Barela for Adafruit Industries
#
# SPDX-License-Identifier: MIT

"""
Enhanced USB HID Device Detection Example for CircuitPython
===========================================================

Comprehensive demonstration of the enhanced adafruit_usb_host_descriptors library
with advanced HID device detection, composite device support, and real-time monitoring.

This example demonstrates:
- Basic device counting and enumeration
- Composite device detection (keyboard+trackpad combos)
- Enhanced input parsing with human-readable output
- Real-time device change monitoring
- Device filtering and configuration
- Performance benchmarking

Hardware Requirements:
- Adafruit board with USB host support (Feather RP2040 USB Host, Fruit Jam, etc.)
- USB keyboards, mice, gamepads, and composite devices for testing

Software Requirements:
- CircuitPython 10.0.0 or highher
- Enhanced adafruit_usb_host_descriptors library

"""

import time
import array
import board
import sys
import usb.core

# Import the enhanced USB host descriptors library
try:
    from adafruit_usb_host_descriptors import (
        # Basic device counting
        count_keyboards, count_mice, count_gamepads,
        # Device information retrieval
        get_keyboard_info, get_mouse_info, get_gamepad_info,
        get_keyboard_device, get_mouse_device, get_gamepad_device,
        # Advanced features
        list_all_hid_devices, force_refresh,
        get_composite_device_info, is_composite_device, get_companion_interfaces,
        # Configuration
        set_cache_timeout, register_device_change_callback, set_device_filter,
        # Utility functions
        is_device_connected, get_info
    )
    ENHANCED_API_AVAILABLE = True
    print("Enhanced HID detection API loaded successfully!")
except ImportError as e:
    print(f"Enhanced HID API not available: {e}")
    print("Please ensure you have the enhanced adafruit_usb_host_descriptors library")
    ENHANCED_API_AVAILABLE = False
    sys.exit(1)

# ============================================================================
# HID REPORT PARSING UTILITIES
# ============================================================================

# HID Usage IDs for common keys (Boot Keyboard Report)
HID_KEY_NAMES = {
    0x04: 'A', 0x05: 'B', 0x06: 'C', 0x07: 'D', 0x08: 'E', 0x09: 'F',
    0x0A: 'G', 0x0B: 'H', 0x0C: 'I', 0x0D: 'J', 0x0E: 'K', 0x0F: 'L',
    0x10: 'M', 0x11: 'N', 0x12: 'O', 0x13: 'P', 0x14: 'Q', 0x15: 'R',
    0x16: 'S', 0x17: 'T', 0x18: 'U', 0x19: 'V', 0x1A: 'W', 0x1B: 'X',
    0x1C: 'Y', 0x1D: 'Z',
    0x1E: '1', 0x1F: '2', 0x20: '3', 0x21: '4', 0x22: '5',
    0x23: '6', 0x24: '7', 0x25: '8', 0x26: '9', 0x27: '0',
    0x28: 'ENTER', 0x29: 'ESC', 0x2A: 'BACKSPACE', 0x2B: 'TAB',
    0x2C: 'SPACE', 0x2D: '-', 0x2E: '=', 0x2F: '[', 0x30: ']',
    0x31: '\\', 0x33: ';', 0x34: "'", 0x35: '`', 0x36: ',',
    0x37: '.', 0x38: '/', 0x39: 'CAPS_LOCK', 0x3A: 'F1', 0x3B: 'F2',
    0x3C: 'F3', 0x3D: 'F4', 0x3E: 'F5', 0x3F: 'F6', 0x40: 'F7',
    0x41: 'F8', 0x42: 'F9', 0x43: 'F10', 0x44: 'F11', 0x45: 'F12'
}

MODIFIER_NAMES = {
    0x01: 'L_CTRL', 0x02: 'L_SHIFT', 0x04: 'L_ALT', 0x08: 'L_GUI',
    0x10: 'R_CTRL', 0x20: 'R_SHIFT', 0x40: 'R_ALT', 0x80: 'R_GUI'
}

def parse_keyboard_report(report_data):
    """
    Parse a keyboard HID report into human-readable format.

    @param report_data: Raw HID report bytes (8 bytes for boot keyboard)
    @return: Dictionary with parsed key information
    """
    if len(report_data) < 8:
        return {"error": "Report too short", "raw": list(report_data)}

    modifier_byte = report_data[0]
    # Byte 1 is reserved
    key_codes = report_data[2:8]  # Up to 6 simultaneous keys

    # Parse modifiers
    active_modifiers = []
    for bit, name in MODIFIER_NAMES.items():
        if modifier_byte & bit:
            active_modifiers.append(name)

    # Parse key codes
    active_keys = []
    for key_code in key_codes:
        if key_code != 0:
            key_name = HID_KEY_NAMES.get(key_code, f"KEY_{key_code:02X}")
            active_keys.append(key_name)

    return {
        "modifiers": active_modifiers,
        "keys": active_keys,
        "raw_modifier": modifier_byte,
        "raw_keys": [k for k in key_codes if k != 0],
        "has_input": bool(active_modifiers or active_keys)
    }

def parse_mouse_report(report_data):
    """
    Parse a mouse HID report into human-readable format.

    @param report_data: Raw HID report bytes (3-4 bytes for boot mouse)
    @return: Dictionary with parsed mouse information
    """
    if len(report_data) < 3:
        return {"error": "Report too short", "raw": list(report_data)}

    buttons = report_data[0]
    x_movement = report_data[1] if report_data[1] < 128 else report_data[1] - 256  # Convert to signed
    y_movement = report_data[2] if report_data[2] < 128 else report_data[2] - 256  # Convert to signed
    wheel = 0

    if len(report_data) > 3:
        wheel = report_data[3] if report_data[3] < 128 else report_data[3] - 256

    # Parse button names
    button_names = []
    if buttons & 0x01:
        button_names.append("LEFT")
    if buttons & 0x02:
        button_names.append("RIGHT")
    if buttons & 0x04:
        button_names.append("MIDDLE")
    if buttons & 0x08:
        button_names.append("BTN4")
    if buttons & 0x10:
        button_names.append("BTN5")

    return {
        "buttons": button_names,
        "x_movement": x_movement,
        "y_movement": y_movement,
        "wheel": wheel,
        "raw_buttons": buttons,
        "has_input": bool(buttons or x_movement or y_movement or wheel)
    }

# ============================================================================
# DEVICE CHANGE MONITORING
# ============================================================================

class DeviceMonitor:
    """Device change monitoring with callbacks and statistics"""

    def __init__(self):
        self.device_history = []
        self.change_count = 0
        register_device_change_callback(self._on_device_change)

    def _on_device_change(self, device_type, action, index):
        """Internal callback for device changes"""
        self.change_count += 1
        timestamp = time.monotonic()

        change_info = {
            'timestamp': timestamp,
            'device_type': device_type,
            'action': action,
            'index': index
        }

        self.device_history.append(change_info)

        # Keep only last 50 changes
        if len(self.device_history) > 50:
            self.device_history.pop(0)

        print(f"[{timestamp:.1f}s] Device {action}: {device_type}[{index}]")

    def get_statistics(self):
        """Get monitoring statistics"""
        return {
            'total_changes': self.change_count,
            'recent_changes': len(self.device_history),
            'history': self.device_history.copy()
        }

# Global device monitor instance
device_monitor = DeviceMonitor()

# ============================================================================
# ENHANCED INPUT READING FUNCTIONS
# ============================================================================

def safe_device_operation(operation_func, *args, **kwargs):
    """
    Safely perform device operations with automatic retry and error handling.
    """
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return operation_func(*args, **kwargs)
        except usb.core.USBError as e:
            if attempt < max_retries - 1:
                print(f"USB error (attempt {attempt + 1}): {e}, retrying...")
                time.sleep(0.1)
                force_refresh()
            else:
                print(f"USB operation failed after {max_retries} attempts: {e}")
                raise
        except Exception as e:
            print(f"Unexpected error in device operation: {e}")
            raise

def enhanced_read_keyboard_input(keyboard_index, duration=5):
    """
    Enhanced keyboard reading with better error handling and parsing.
    """
    print(f"\n=== Reading from Keyboard[{keyboard_index}] ===")

    try:
        device = safe_device_operation(get_keyboard_device, keyboard_index)
        interface_index, endpoint_address = safe_device_operation(get_keyboard_info, keyboard_index)

        if device is None or endpoint_address is None:
            print(f"Keyboard[{keyboard_index}] not available")
            return

        print(f"Device: {device.manufacturer} {device.product}")
        print(f"VID:PID: {device.idVendor:04x}:{device.idProduct:04x}")
        print(f"Interface: {interface_index}, Endpoint: 0x{endpoint_address:02x}")

        # Check if this is part of a composite device
        is_composite, other_types = is_composite_device('keyboard', keyboard_index)
        if is_composite:
            print(f"Composite device - also has: {', '.join(other_types)}")

        # Setup device
        device.set_configuration()
        if device.is_kernel_driver_active(interface_index):
            device.detach_kernel_driver(interface_index)

        buf = array.array("B", [0] * 8)
        print(f"\nPress keys for {duration} seconds (parsed output will appear):")

        start_time = time.monotonic()
        last_report = None
        key_press_count = 0

        while time.monotonic() - start_time < duration:
            try:
                count = device.read(endpoint_address, buf, timeout=100)
                if count > 0:
                    # Only process if report changed (avoid spam from key repeat)
                    current_report = bytes(buf[:count])
                    if current_report != last_report:
                        parsed = parse_keyboard_report(buf)

                        if parsed.get("has_input"):
                            key_press_count += 1
                            output_parts = []

                            if parsed["modifiers"]:
                                output_parts.append(f"Modifiers: {'+'.join(parsed['modifiers'])}")
                            if parsed["keys"]:
                                output_parts.append(f"Keys: {'+'.join(parsed['keys'])}")

                            print(f"  [{key_press_count:2d}] {' | '.join(output_parts)}")

                        last_report = current_report

            except usb.core.USBTimeoutError:
                pass  # Normal timeout
            except usb.core.USBError as e:
                print(f"  USB read error: {e}")
                break

        print(f"Keyboard reading complete. Detected {key_press_count} key events.")

    except Exception as e:
        print(f"Error in enhanced keyboard reading: {e}")

def enhanced_read_mouse_input(mouse_index, duration=5):
    """
    Enhanced mouse reading with better error handling and parsing.
    """
    print(f"\n=== Reading from Mouse[{mouse_index}] ===")

    try:
        device = safe_device_operation(get_mouse_device, mouse_index)
        interface_index, endpoint_address = safe_device_operation(get_mouse_info, mouse_index)

        if device is None or endpoint_address is None:
            print(f"Mouse[{mouse_index}] not available")
            return

        print(f"Device: {device.manufacturer} {device.product}")
        print(f"VID:PID: {device.idVendor:04x}:{device.idProduct:04x}")
        print(f"Interface: {interface_index}, Endpoint: 0x{endpoint_address:02x}")

        # Check if this is part of a composite device
        is_composite, other_types = is_composite_device('mouse', mouse_index)
        if is_composite:
            print(f"Composite device - also has: {', '.join(other_types)}")
            print("(This might be a trackpad from a keyboard+trackpad combo)")

        # Setup device
        device.set_configuration()
        if device.is_kernel_driver_active(interface_index):
            device.detach_kernel_driver(interface_index)

        buf = array.array("B", [0] * 4)
        print(f"\nMove mouse/trackpad and click buttons for {duration} seconds:")

        start_time = time.monotonic()
        last_report = None
        mouse_event_count = 0
        total_x_movement = 0
        total_y_movement = 0

        while time.monotonic() - start_time < duration:
            try:
                count = device.read(endpoint_address, buf, timeout=100)
                if count > 0:
                    current_report = bytes(buf[:count])
                    if current_report != last_report:
                        parsed = parse_mouse_report(buf)

                        if parsed.get("has_input"):
                            mouse_event_count += 1
                            total_x_movement += abs(parsed["x_movement"])
                            total_y_movement += abs(parsed["y_movement"])

                            output_parts = []

                            if parsed["buttons"]:
                                output_parts.append(f"Buttons: {'+'.join(parsed['buttons'])}")
                            if parsed["x_movement"] or parsed["y_movement"]:
                                output_parts.append(f"Move: X{parsed['x_movement']:+d} Y{parsed['y_movement']:+d}")
                            if parsed["wheel"]:
                                output_parts.append(f"Wheel: {parsed['wheel']:+d}")

                            print(f"  [{mouse_event_count:2d}] {' | '.join(output_parts)}")

                        last_report = current_report

            except usb.core.USBTimeoutError:
                pass  # Normal timeout
            except usb.core.USBError as e:
                print(f"  USB read error: {e}")
                break

        print(f"Mouse reading complete. Detected {mouse_event_count} mouse events.")
        print(f"Total movement: X={total_x_movement} Y={total_y_movement}")

    except Exception as e:
        print(f"Error in enhanced mouse reading: {e}")

def read_composite_device(keyboard_index, duration=5):
    """
    Read from both keyboard and trackpad interfaces of a composite device.
    """
    print(f"\n=== Reading Composite Device (Keyboard[{keyboard_index}]) ===")

    # Verify this is a composite device with mouse interface
    is_composite, other_types = is_composite_device('keyboard', keyboard_index)
    if not is_composite or 'mouse' not in other_types:
        print(f"Keyboard[{keyboard_index}] is not a composite device with trackpad")
        return

    try:
        # Get keyboard interfaces
        kbd_device = get_keyboard_device(keyboard_index)
        kbd_interface, kbd_endpoint = get_keyboard_info(keyboard_index)

        # Get trackpad interface from companion interfaces
        companions = get_companion_interfaces('keyboard', keyboard_index)
        trackpad_info = companions['mouse']
        trackpad_interface = trackpad_info['interface_index']
        trackpad_endpoint = trackpad_info['endpoint_address']

        print(f"Composite device: {kbd_device.product}")
        print(f"  Keyboard interface: {kbd_interface}, endpoint: 0x{kbd_endpoint:02x}")
        print(f"  Trackpad interface: {trackpad_interface}, endpoint: 0x{trackpad_endpoint:02x}")

        # Setup device
        kbd_device.set_configuration()

        # Detach kernel drivers for both interfaces
        if kbd_device.is_kernel_driver_active(kbd_interface):
            kbd_device.detach_kernel_driver(kbd_interface)
        if trackpad_interface != kbd_interface and kbd_device.is_kernel_driver_active(trackpad_interface):
            kbd_device.detach_kernel_driver(trackpad_interface)

        kbd_buf = array.array("B", [0] * 8)
        mouse_buf = array.array("B", [0] * 4)

        print(f"\nUse both keyboard and trackpad for {duration} seconds:")
        print("(Events from both interfaces will be shown)")

        start_time = time.monotonic()
        last_kbd_report = None
        last_mouse_report = None
        kbd_events = 0
        mouse_events = 0

        while time.monotonic() - start_time < duration:
            try:
                # Try to read keyboard
                try:
                    count = kbd_device.read(kbd_endpoint, kbd_buf, timeout=10)
                    if count > 0:
                        current_kbd_report = bytes(kbd_buf[:count])
                        if current_kbd_report != last_kbd_report:
                            parsed = parse_keyboard_report(kbd_buf)
                            if parsed.get("has_input"):
                                kbd_events += 1
                                output_parts = []
                                if parsed["modifiers"]:
                                    output_parts.append(f"Mods: {'+'.join(parsed['modifiers'])}")
                                if parsed["keys"]:
                                    output_parts.append(f"Keys: {'+'.join(parsed['keys'])}")
                                print(f"  🎹 KEYBOARD[{kbd_events:2d}]: {' | '.join(output_parts)}")
                            last_kbd_report = current_kbd_report
                except usb.core.USBTimeoutError:
                    pass

                # Try to read trackpad
                try:
                    count = kbd_device.read(trackpad_endpoint, mouse_buf, timeout=10)
                    if count > 0:
                        current_mouse_report = bytes(mouse_buf[:count])
                        if current_mouse_report != last_mouse_report:
                            parsed = parse_mouse_report(mouse_buf)
                            if parsed.get("has_input"):
                                mouse_events += 1
                                output_parts = []
                                if parsed["buttons"]:
                                    output_parts.append(f"Btns: {'+'.join(parsed['buttons'])}")
                                if parsed["x_movement"] or parsed["y_movement"]:
                                    output_parts.append(f"Move: X{parsed['x_movement']:+d} Y{parsed['y_movement']:+d}")
                                if parsed["wheel"]:
                                    output_parts.append(f"Wheel: {parsed['wheel']:+d}")
                                print(f"  🖱️  TRACKPAD[{mouse_events:2d}]: {' | '.join(output_parts)}")
                            last_mouse_report = current_mouse_report
                except usb.core.USBTimeoutError:
                    pass

            except usb.core.USBError as e:
                print(f"USB error: {e}")
                break

        print(f"\nComposite device reading complete:")
        print(f"  Keyboard events: {kbd_events}")
        print(f"  Trackpad events: {mouse_events}")

    except Exception as e:
        print(f"Error reading composite device: {e}")

# ============================================================================
# DEVICE DISCOVERY AND ANALYSIS
# ============================================================================

def analyze_all_devices():
    """
    Comprehensive analysis of all connected HID devices.
    """
    print("\n" + "="*60)
    print("COMPREHENSIVE HID DEVICE ANALYSIS")
    print("="*60)

    # Force fresh scan
    force_refresh()

    # Get device counts
    keyboards = count_keyboards()
    mice = count_mice()
    gamepads = count_gamepads()

    print(f"\nDevice Summary:")
    print(f"  Keyboards: {keyboards}")
    print(f"  Mice:      {mice}")
    print(f"  Gamepads:  {gamepads}")
    print(f"  Total:     {keyboards + mice + gamepads}")

    # Detailed device information
    summary = list_all_hid_devices()

    print(f"\nDetailed Device Information:")
    print("-" * 40)

    # Analyze keyboards
    if summary['keyboards']['count'] > 0:
        print(f"\n🎹 KEYBOARDS ({summary['keyboards']['count']}):")
        for device in summary['keyboards']['devices']:
            print(f"  [{device['index']}] {device['manufacturer']} {device['product']}")
            print(f"      VID:PID = {device['vid']:04x}:{device['pid']:04x}")
            print(f"      Interface: {device['interface_index']}, Endpoint: 0x{device['endpoint_address']:02x}")

            # Check for composite capabilities
            is_composite, other_types = is_composite_device('keyboard', device['index'])
            if is_composite:
                print(f"      🔗 Composite device with: {', '.join(other_types)}")

            # Check connectivity
            connected = is_device_connected('keyboard', device['index'])
            print(f"      Status: {'🟢 Connected' if connected else '🔴 Disconnected'}")

    # Analyze mice
    if summary['mice']['count'] > 0:
        print(f"\n🖱️  MICE ({summary['mice']['count']}):")
        for device in summary['mice']['devices']:
            print(f"  [{device['index']}] {device['manufacturer']} {device['product']}")
            print(f"      VID:PID = {device['vid']:04x}:{device['pid']:04x}")
            print(f"      Interface: {device['interface_index']}, Endpoint: 0x{device['endpoint_address']:02x}")

            # Check for composite capabilities
            is_composite, other_types = is_composite_device('mouse', device['index'])
            if is_composite:
                print(f"      🔗 Composite device with: {', '.join(other_types)}")
                print(f"      (This might be a trackpad from a keyboard+trackpad combo)")

            # Check connectivity
            connected = is_device_connected('mouse', device['index'])
            print(f"      Status: {'🟢 Connected' if connected else '🔴 Disconnected'}")

    # Analyze gamepads
    if summary['gamepads']['count'] > 0:
        print(f"\n🎮 GAMEPADS ({summary['gamepads']['count']}):")
        for device in summary['gamepads']['devices']:
            print(f"  [{device['index']}] {device['manufacturer']} {device['product']}")
            print(f"      VID:PID = {device['vid']:04x}:{device['pid']:04x}")
            print(f"      Interface: {device['interface_index']}, Endpoint: 0x{device['endpoint_address']:02x}")

            # Check connectivity
            connected = is_device_connected('gamepad', device['index'])
            print(f"      Status: {'🟢 Connected' if connected else '🔴 Disconnected'}")

    # Analyze composite devices
    composite_devices = get_composite_device_info()
    if composite_devices:
        print(f"\n🔗 COMPOSITE DEVICES ({len(composite_devices)}):")
        for device_id, info in composite_devices.items():
            print(f"  {info['product']}")
            print(f"    Device ID: {device_id}")
            print(f"    Interface types: {', '.join(info['types'])}")

            # Show how to access each interface
            for device_type in info['types']:
                if device_type == 'keyboard':
                    for i in range(keyboards):
                        kbd_device = get_keyboard_device(i)
                        kbd_id = f"{kbd_device.idVendor:04x}:{kbd_device.idProduct:04x}:{getattr(kbd_device, 'serial_number', 'no_serial')}"
                        if kbd_id == device_id:
                            print(f"    -> Access keyboard via: get_keyboard_info({i})")
                            break
                elif device_type == 'mouse':
                    for i in range(mice):
                        mouse_device = get_mouse_device(i)
                        mouse_id = f"{mouse_device.idVendor:04x}:{mouse_device.idProduct:04x}:{getattr(mouse_device, 'serial_number', 'no_serial')}"
                        if mouse_id == device_id:
                            print(f"    -> Access mouse/trackpad via: get_mouse_info({i})")
                            break

def benchmark_performance():
    """
    Benchmark the performance of device detection operations.
    """
    print(f"\n🔍 PERFORMANCE BENCHMARK")
    print("-" * 30)

    import gc

    # Warm up
    force_refresh()

    # Benchmark full device scan
    gc.collect()
    start_time = time.monotonic()
    force_refresh()
    scan_time = time.monotonic() - start_time

    # Benchmark cached access
    start_time = time.monotonic()
    keyboards = count_keyboards()
    mice = count_mice()
    gamepads = count_gamepads()
    cache_time = time.monotonic() - start_time

    # Benchmark device info access
    start_time = time.monotonic()
    for i in range(keyboards):
        get_keyboard_info(i)
    for i in range(mice):
        get_mouse_info(i)
    for i in range(gamepads):
        get_gamepad_info(i)
    info_time = time.monotonic() - start_time

    # Benchmark composite device operations
    start_time = time.monotonic()
    get_composite_device_info()
    for i in range(keyboards):
        is_composite_device('keyboard', i)
    composite_time = time.monotonic() - start_time

    print(f"Full device scan:      {scan_time*1000:6.1f} ms")
    print(f"Cached device counts:  {cache_time*1000:6.3f} ms")
    print(f"Device info access:    {info_time*1000:6.1f} ms")
    print(f"Composite operations:  {composite_time*1000:6.1f} ms")
    print(f"Devices found: {keyboards} kbd, {mice} mouse, {gamepads} gamepad")

def demonstrate_device_filtering():
    """
    Demonstrate device filtering capabilities.
    """
    print(f"\n🔍 DEVICE FILTERING DEMONSTRATION")
    print("-" * 40)

    # Show all devices first
    print("Before filtering:")
    summary = list_all_hid_devices()
    total_before = sum(info['count'] for info in summary.values())
    print(f"  Total devices: {total_before}")

    if total_before == 0:
        print("  No devices to filter. Connect some devices first.")
        return

    # Get a VID to filter by (use first keyboard if available)
    if summary['keyboards']['count'] > 0:
        test_vid = summary['keyboards']['devices'][0]['vid']
        print(f"\nFiltering to only allow VID 0x{test_vid:04x}...")

        # Apply filter
        set_device_filter(allowed_vids={test_vid})

        # Force refresh and check results
        force_refresh()
        filtered_summary = list_all_hid_devices()
        total_after = sum(info['count'] for info in filtered_summary.values())

        print(f"After filtering:")
        print(f"  Total devices: {total_after}")
        for device_type, info in filtered_summary.items():
            if info['count'] > 0:
                print(f"  {device_type}: {info['count']}")

        # Clear filter
        print(f"\nClearing filter...")
        set_device_filter(allowed_vids=None)
        force_refresh()

        restored_summary = list_all_hid_devices()
        total_restored = sum(info['count'] for info in restored_summary.values())
        print(f"After clearing filter:")
        print(f"  Total devices: {total_restored}")

def continuous_monitoring(duration=30):
    """
    Demonstrate continuous device monitoring.
    """
    print(f"\n📡 CONTINUOUS DEVICE MONITORING")
    print(f"Duration: {duration} seconds")
    print("-" * 40)
    print("Connect and disconnect devices to see real-time detection!")
    print("(Device changes will be logged automatically)")

    start_time = time.monotonic()
    last_summary = None
    check_interval = 1.0  # Check every second

    try:
        while time.monotonic() - start_time < duration:
            current_time = time.monotonic() - start_time

            # Check for device changes
            force_refresh()
            current_summary = list_all_hid_devices()

            # Show periodic status updates
            if int(current_time) % 10 == 0 and int(current_time) > 0:
                total_devices = sum(info['count'] for info in current_summary.values())
                print(f"[{current_time:5.0f}s] Status: {total_devices} total devices connected")

            last_summary = current_summary
            time.sleep(check_interval)

    except KeyboardInterrupt:
        print("\nMonitoring stopped by user")

    # Show monitoring statistics
    stats = device_monitor.get_statistics()
    print(f"\nMonitoring Statistics:")
    print(f"  Total device changes detected: {stats['total_changes']}")
    print(f"  Recent changes in history: {stats['recent_changes']}")

    if stats['recent_changes'] > 0:
        print(f"  Recent changes:")
        for change in stats['history'][-5:]:  # Show last 5 changes
            print(f"    {change['timestamp']:.1f}s: {change['device_type']} {change['action']}")

# ============================================================================
# MAIN DEMONSTRATION FUNCTION
# ============================================================================

def main():
    """
    Main demonstration function showcasing all enhanced features.
    """
    print("Enhanced USB HID Device Detection Example")
    print("=========================================")
    print(f"Running on: {board.board_id}")
    print(f"CircuitPython version: {board.__name__}")

    # Configure library settings
    print(f"\nConfiguring library settings...")
    set_cache_timeout(0.5)  # 500ms cache timeout for responsive demo

    # Initial device analysis
    analyze_all_devices()

    # Performance benchmark
    benchmark_performance()

    # Quick input demos if devices are available
    keyboards = count_keyboards()
    mice = count_mice()

    if keyboards > 0:
        print(f"\n⌨️  Quick keyboard demo (first 3 seconds)...")
        enhanced_read_keyboard_input(0, duration=3)

    if mice > 0:
        print(f"\n🖱️  Quick mouse demo (first 3 seconds)...")
        enhanced_read_mouse_input(0, duration=3)

    # Check for composite devices
    composite_found = False
    for i in range(keyboards):
        is_composite, other_types = is_composite_device('keyboard', i)
        if is_composite and 'mouse' in other_types:
            print(f"\n🔗 Quick composite device demo (3 seconds)...")
            read_composite_device(i, duration=3)
            composite_found = True
            break

    if not composite_found and keyboards > 0:
        print(f"\n💡 Tip: Try connecting a keyboard with integrated trackpad to see composite device features!")

    # Device filtering demo
    demonstrate_device_filtering()

    print(f"\n🎉 Basic demonstration complete!")
    print(f"\nFor extended testing:")
    print(f"  - Call analyze_all_devices() for detailed analysis")
    print(f"  - Call continuous_monitoring(duration) to monitor device changes")
    print(f"  - Call enhanced_read_keyboard_input(index) to test keyboard input")
    print(f"  - Call enhanced_read_mouse_input(index) to test mouse input")
    print(f"  - Call read_composite_device(index) for composite device testing")

if __name__ == "__main__":
    if not ENHANCED_API_AVAILABLE:
        print("Enhanced API not available. Cannot run demonstration.")
    else:
        try:
            main()
        except KeyboardInterrupt:
            print("\nDemo interrupted by user")
        except Exception as e:
            print(f"Demo error: {e}")
            import traceback
            traceback.print_exc()
