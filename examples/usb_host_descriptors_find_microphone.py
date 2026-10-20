# SPDX-FileCopyrightText: Copyright (c) 2026 Tim Cocks for Adafruit Industries
#
# SPDX-License-Identifier: MIT
"""Find a USB microphone among the attached USB devices and print the audio
formats its descriptors offer."""

import time

import adafruit_usb_host_descriptors

device = None
while device is None:
    device = adafruit_usb_host_descriptors.find_microphone()
    if device is None:
        print("Plug a USB microphone or webcam into the USB host port")
        time.sleep(2)

print(f"Microphone {device.idVendor:04x}:{device.idProduct:04x}")
print("  manufacturer:", device.manufacturer)
print("  product:", device.product)

formats = adafruit_usb_host_descriptors.find_microphone_formats(device)
for audio_format in formats:
    print(audio_format)
    print("  interface:", audio_format.interface, "alternate setting:", audio_format.alternate)
    print(f"  endpoint: 0x{audio_format.endpoint:02x}")
    print("  max packet size:", audio_format.max_packet_size)
    print("  channels:", audio_format.channel_count)
    print(
        "  bits per sample:",
        audio_format.bits_per_sample,
        "in",
        audio_format.bytes_per_sample,
        "bytes,",
        "signed" if audio_format.samples_signed else "unsigned",
    )
    if audio_format.sample_rate_range:
        low, high = audio_format.sample_rate_range
        print(f"  sample rates: any from {low} to {high} Hz")
    else:
        print("  sample rates:", audio_format.sample_rates, "Hz")
    print("  sample rate can be set:", audio_format.rate_control)

closest = adafruit_usb_host_descriptors.choose_microphone_format(
    formats, sample_rate=16000, bit_depth=16, channel_count=1
)
print("Closest to 16 kHz, 16 bit mono:", closest, "at", closest.nearest_rate(16000), "Hz")
