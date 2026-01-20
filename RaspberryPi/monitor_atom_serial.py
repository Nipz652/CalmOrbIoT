#!/usr/bin/env python3
"""
Simple Serial Monitor for Atom Echo
Shows exactly what data is being received from the device.
"""

import serial
import time
import sys

def monitor_serial():
    port = "/dev/ttyUSB0"
    baud = 921600

    print("=" * 60)
    print("Atom Echo Serial Monitor")
    print("=" * 60)
    print(f"\nOpening {port} at {baud} baud...")
    print("This will show ALL data received from Atom Echo.\n")
    print("Expected from NEW firmware:")
    print("  - Startup messages: 'READY', 'Speaker volume set to 255'")
    print("  - Heartbeat every 5 seconds: 'HEARTBEAT'")
    print("\nIf you see binary/garbage data, OLD firmware is still running.\n")
    print("Monitoring for 30 seconds... Press Ctrl+C to stop early.\n")
    print("=" * 60)

    try:
        # Stop the service first
        import subprocess
        print("Stopping distress service...")
        subprocess.run(["sudo", "systemctl", "stop", "distress.service"],
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)

        # Open serial without DTR reset
        ser = serial.Serial(
            port=port,
            baudrate=baud,
            timeout=0.1,
            dsrdtr=False,
            rtscts=False
        )

        print("✓ Serial port opened\n")
        print("Received data:\n")

        start_time = time.time()
        line_buffer = ""
        binary_count = 0
        text_count = 0

        while time.time() - start_time < 30:
            if ser.in_waiting > 0:
                try:
                    # Try to read as text
                    data = ser.read(ser.in_waiting)

                    # Check if it's printable text
                    try:
                        text = data.decode('utf-8', errors='strict')
                        # Print each line
                        for char in text:
                            if char == '\n':
                                if line_buffer:
                                    print(f"  TEXT: {line_buffer}")
                                    text_count += 1
                                line_buffer = ""
                            elif char == '\r':
                                pass
                            elif ord(char) >= 32 or char == '\t':
                                line_buffer += char
                    except UnicodeDecodeError:
                        # Binary data - print first 32 bytes as hex
                        binary_count += 1
                        if binary_count == 1:
                            print(f"  BINARY DATA (first 32 bytes): {data[:32].hex()}")
                            print(f"  ... receiving continuous binary stream (old firmware with mic streaming)")
                        elif binary_count % 100 == 0:
                            print(f"  ... still receiving binary data ({binary_count} chunks)")

                except Exception as e:
                    print(f"  ERROR reading: {e}")

            time.sleep(0.01)

        # Print remaining buffer
        if line_buffer:
            print(f"  TEXT: {line_buffer}")

        print("\n" + "=" * 60)
        print("Monitor Complete")
        print("=" * 60)
        print(f"\nStatistics:")
        print(f"  Text messages: {text_count}")
        print(f"  Binary chunks: {binary_count}")

        if binary_count > 0:
            print("\n⚠️  OLD FIRMWARE IS STILL RUNNING!")
            print("    The Atom Echo is streaming binary microphone data.")
            print("    The new firmware was NOT successfully flashed.")
            print("\nNext steps:")
            print("  1. Re-upload the firmware")
            print("  2. Check PlatformIO upload output for errors")
            print("  3. Try manual reset after upload")
        elif text_count > 0:
            print("\n✓ NEW FIRMWARE IS RUNNING!")
            print("  Atom Echo is sending text messages as expected.")
        else:
            print("\n⚠️  NO DATA RECEIVED!")
            print("  Possible issues:")
            print("    - Wrong baud rate")
            print("    - Hardware not connected")
            print("    - Firmware not running")

        ser.close()

        # Restart service
        print("\nRestarting distress service...")
        subprocess.run(["sudo", "systemctl", "start", "distress.service"],
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    except serial.SerialException as e:
        print(f"✗ Serial error: {e}")
        return 1
    except KeyboardInterrupt:
        print("\n\nStopped by user")
        ser.close()
        subprocess.run(["sudo", "systemctl", "start", "distress.service"],
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(monitor_serial())
