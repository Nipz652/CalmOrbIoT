#!/usr/bin/env python3
"""
Test ESP32 Connection
Listens for UDP packets from ESP32 and displays the data.
"""

import socket
import time

# ESP32 sends to this port
UDP_LISTEN_PORT = 4210
ESP32_IP = "192.168.4.1"
ESP32_CMD_PORT = 5006

def test_receive():
    """Listen for data from ESP32."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", UDP_LISTEN_PORT))
    sock.settimeout(10)  # 10 second timeout

    print(f"Listening for ESP32 data on UDP port {UDP_LISTEN_PORT}...")
    print("Waiting for ESP32 to send data (squeeze the ball or shake it)...")
    print("-" * 60)

    try:
        while True:
            try:
                data, addr = sock.recvfrom(1024)
                message = data.decode('utf-8')
                print(f"\n[{time.strftime('%H:%M:%S')}] From {addr}:")

                # Parse the message
                fields = message.split(',')
                for field in fields:
                    if ':' in field:
                        key, value = field.split(':', 1)
                        print(f"  {key}: {value}")

                print("-" * 60)

            except socket.timeout:
                print(".", end="", flush=True)

    except KeyboardInterrupt:
        print("\n\nStopping listener...")
    finally:
        sock.close()


def test_send_command(command):
    """Send a command to ESP32."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        sock.sendto(command.encode(), (ESP32_IP, ESP32_CMD_PORT))
        print(f"Sent to ESP32: {command}")
    except Exception as e:
        print(f"Error sending: {e}")
    finally:
        sock.close()


def test_ping():
    """Test basic network connectivity to ESP32."""
    import subprocess

    print(f"Pinging ESP32 at {ESP32_IP}...")
    result = subprocess.run(
        ["ping", "-c", "3", ESP32_IP],
        capture_output=True,
        text=True
    )
    print(result.stdout)
    if result.returncode == 0:
        print("ESP32 is reachable!")
        return True
    else:
        print("Cannot reach ESP32")
        return False


if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("ESP32 Connection Test")
    print("=" * 60)

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "ping":
            test_ping()
        elif cmd == "send":
            if len(sys.argv) > 2:
                test_send_command(sys.argv[2])
            else:
                print("Usage: python test_esp32_connection.py send 'PLAY:1'")
        elif cmd == "listen":
            test_receive()
        else:
            print("Unknown command")
    else:
        # Default: ping then listen
        print("\n1. Testing connectivity...")
        if test_ping():
            print("\n2. Listening for sensor data...")
            print("   (Interact with the stress ball to see data)")
            print("   Press Ctrl+C to stop\n")
            test_receive()
