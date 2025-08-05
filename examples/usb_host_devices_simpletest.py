# SPDX-FileCopyrightText: Copyright (c) 2025 Anne Barela for Adafruit Industries
#
# SPDX-License-Identifier: MIT

"""
Simple USB Device Monitor
=========================

A simple program that continuously monitors USB host ports for connected devices.
Automatically starts monitoring and detects when devices are plugged in or unplugged.

This program:
- Loops continuously checking for USB devices every 5 seconds
- Detects device additions and removals automatically
- Shows basic device information
- Handles composite devices (keyboard+trackpad combos)
- Runs until stopped with Ctrl+C

Hardware Requirements:
- Adafruit board with USB host support (Feather RP2040 USB Host, Fruit Jam, etc.)
- USB devices can be connected/disconnected during operation

Software Requirements:
- CircuitPython 9.0+ with usb_host support
- Enhanced adafruit_usb_host_descriptors library

Usage:
- Simply run this program
- Connect and disconnect USB devices to see detection
- Press Ctrl+C to stop monitoring

"""

import time
import board

# Import the enhanced USB host descriptors library
try:
    from adafruit_usb_host_descriptors import (
        count_keyboards, count_mice, count_gamepads,
        list_all_hid_devices, get_composite_device_info,
        force_refresh, is_device_connected
    )
    print("Enhanced USB host descriptors library loaded")
except ImportError as e:
    print("Library import failed: {}".format(e))
    print("Please ensure you have the enhanced " +
          "adafruit_usb_host_descriptors library")
    exit(1)

class SimpleDeviceMonitor:
    """Simple USB device monitor with change detection"""

    def __init__(self):
        self.last_device_state = None
        self.loop_count = 0
        self.total_changes = 0

    def get_current_device_state(self):
        """Get current device state as a comparable dictionary"""
        try:
            # Force fresh scan to detect changes
            force_refresh()

            # Get device counts
            keyboards = count_keyboards()
            mice = count_mice()
            gamepads = count_gamepads()

            # Get detailed device info
            devices = list_all_hid_devices()

            # Create a state snapshot
            state = {
                'counts': {
                    'keyboards': keyboards,
                    'mice': mice,
                    'gamepads': gamepads,
                    'total': keyboards + mice + gamepads
                },
                'devices': {}
            }

            # Store device details for comparison
            for device_type in ['keyboards', 'mice', 'gamepads']:
                state['devices'][device_type] = []
                for device in devices[device_type]['devices']:
                    # Create a simple identifier for each device
                    device_id = "{:04x}:{:04x}:{}:{}".format(
                        device['vid'], device['pid'],
                        device['manufacturer'], device['product'])
                    state['devices'][device_type].append({
                        'id': device_id,
                        'index': device['index'],
                        'manufacturer': device['manufacturer'],
                        'product': device['product'],
                        'vid': device['vid'],
                        'pid': device['pid']
                    })

            return state

        except Exception as e:
            # Return empty state on error to prevent crash
            print("  WARNING: Could not get device state: {}".format(e))
            return {
                'counts': {'keyboards': 0, 'mice': 0, 'gamepads': 0,
                           'total': 0},
                'devices': {'keyboards': [], 'mice': [], 'gamepads': []}
            }

    def detect_changes(self, current_state):
        """Detect and report changes between current and last state"""
        if self.last_device_state is None:
            # First run - no change detection needed, just note it's first run
            return

        changes_detected = False

        # Proper singular forms mapping
        singular_forms = {
            'keyboards': 'keyboard',
            'mice': 'mouse',
            'gamepads': 'gamepad'
        }

        # Check for count changes
        for device_type in ['keyboards', 'mice', 'gamepads']:
            current_count = current_state['counts'][device_type]
            last_count = self.last_device_state['counts'][device_type]

            if current_count != last_count:
                changes_detected = True
                change = current_count - last_count
                if change > 0:
                    print("  + {}: +{} (now {})".format(
                        device_type, change, current_count))
                else:
                    print("  - {}: {} (now {})".format(
                        device_type, change, current_count))

        # Detect specific device changes
        for device_type in ['keyboards', 'mice', 'gamepads']:
            current_devices = {d['id']: d for d in
                               current_state['devices'][device_type]}
            last_devices = {d['id']: d for d in
                            self.last_device_state['devices'][device_type]}

            device_type_singular = singular_forms[device_type]

            # Find new devices
            for device_id, device in current_devices.items():
                if device_id not in last_devices:
                    changes_detected = True
                    print("  CONNECTED: {} {} ({})".format(
                        device['manufacturer'], device['product'],
                        device_type_singular))

            # Find removed devices
            for device_id, device in last_devices.items():
                if device_id not in current_devices:
                    changes_detected = True
                    print("  DISCONNECTED: {} {} ({})".format(
                        device['manufacturer'], device['product'],
                        device_type_singular))

        if changes_detected:
            self.total_changes += 1

    def report_current_devices(self, state):
        """Report current connected devices"""
        total = state['counts']['total']

        if total == 0:
            print("  No HID devices connected")
        else:
            print("  Current devices ({} total):".format(total))

            for device_type in ['keyboards', 'mice', 'gamepads']:
                devices = state['devices'][device_type]
                if devices:
                    # Manual capitalization for CircuitPython compatibility
                    type_name = device_type[0].upper() + device_type[1:]
                    print("     {}: {}".format(type_name, len(devices)))
                    for device in devices:
                        print("       [{}] {} {}".format(
                            device['index'], device['manufacturer'],
                            device['product']))

            # Check for composite devices
            composite_devices = get_composite_device_info()
            if composite_devices:
                print("     Composite devices: {}".format(
                    len(composite_devices)))
                for device_id, info in composite_devices.items():
                    print("       {} ({})".format(
                        info['product'], ', '.join(info['types'])))

    def check_device_connectivity(self, state):
        """Check if previously detected devices are still responding"""
        connectivity_issues = []

        # Proper singular forms mapping
        singular_forms = {
            'keyboards': 'keyboard',
            'mice': 'mouse',  # Fix: was becoming 'mic' incorrectly
            'gamepads': 'gamepad'
        }

        for device_type in ['keyboards', 'mice', 'gamepads']:
            for device in state['devices'][device_type]:
                device_type_singular = singular_forms[device_type]
                connected = is_device_connected(device_type_singular,
                                                device['index'])
                if not connected:
                    connectivity_issues.append("{}[{}]".format(
                        device_type_singular, device['index']))

        if connectivity_issues:
            print("  WARNING: Connectivity issues: {}".format(
                ', '.join(connectivity_issues)))

    def run(self):
        """Main monitoring loop"""
        print("Simple USB Device Monitor")
        print("=" * 25)
        print("Running on: {}".format(board.board_id))
        print("Monitoring USB host ports for device changes...")
        print("Connect/disconnect devices to see detection in action")
        print()
        print("IMPORTANT: Press Ctrl+C to stop monitoring at any time")
        print("           Monitoring will continue until interrupted")
        print()

        start_time = time.monotonic()

        try:
            while True:
                self.loop_count += 1

                print("Loop #{} - Checking devices...".format(
                    self.loop_count))

                try:
                    # Get current device state
                    current_state = self.get_current_device_state()

                    # Detect and report changes
                    self.detect_changes(current_state)

                    # Always show current device info each loop
                    self.report_current_devices(current_state)

                    # Check device connectivity (optional diagnostic)
                    if current_state['counts']['total'] > 0:
                        self.check_device_connectivity(current_state)

                    # Update state for next iteration
                    self.last_device_state = current_state

                except KeyboardInterrupt:
                    # Break out of inner loop on Ctrl+C
                    raise
                except Exception as e:
                    print("  ERROR: Error during device check: {}".format(e))

                # Show statistics periodically
                if self.loop_count % 10 == 0:
                    print("  Statistics: {} checks, {} changes detected".format(
                        self.loop_count, self.total_changes))

                print()  # Empty line for readability

                # Wait 5 seconds before next check
                time.sleep(5.0)

        except KeyboardInterrupt:
            # Clean shutdown on Ctrl+C
            runtime = time.monotonic() - start_time
            print("\nMonitoring stopped by user (Ctrl+C pressed)")
            print("Final statistics:")
            print("   Total checks: {}".format(self.loop_count))
            print("   Changes detected: {}".format(self.total_changes))
            print("   Runtime: {:.1f} seconds".format(runtime))
            print("Thank you for using USB Device Monitor!")

# Main execution
if __name__ == "__main__":
    print("Starting USB Device Monitor...")
    print("Press Ctrl+C at any time to stop monitoring")
    print()

    try:
        # Create and run the continuous monitor
        monitor = SimpleDeviceMonitor()
        monitor.run()

    except KeyboardInterrupt:
        print("\nProgram interrupted by user (Ctrl+C)")
        print("Goodbye!")
    except Exception as e:
        print("\nError starting monitor: {}".format(e))
        print("Please check your USB host hardware and library installation")
        print("Program terminated.")
