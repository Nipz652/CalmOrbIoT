"""
Access Point Manager for Live Streaming

Switches wlan0 between client mode and AP mode for mobile streaming.
wlan1 remains connected to ESP32 for distress detection.

Architecture:
- wlan0: Client mode (home WiFi - dev only) OR AP mode (for mobile streaming)
- wlan1: Always connected to ESP32 via WiFi

Production: Home WiFi not used, wlan0 dedicated to streaming AP
Development: Home WiFi temporarily disconnected during streaming

Dependencies:
- hostapd: Access Point daemon
- dnsmasq: DHCP server for AP mode
- wpa_supplicant: Client mode WiFi management
"""

import asyncio
import subprocess
import os
import re
import secrets
import string
import logging
from typing import Optional, Tuple
from dataclasses import dataclass
from enum import Enum

# Import settings
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

logger = logging.getLogger(__name__)


class APState(Enum):
    """Access Point state machine states"""
    CLIENT_MODE = "client_mode"
    AP_STARTING = "ap_starting"
    AP_READY = "ap_ready"
    AP_STOPPING = "ap_stopping"
    AP_FAILED = "ap_failed"


@dataclass
class WiFiCredentials:
    """Stored Wi-Fi credentials for restoration"""
    ssid: str
    password: str
    key_mgmt: str = "WPA-PSK"


class APManager:
    """
    Manages Wi-Fi Access Point mode for live streaming.

    Flow:
    1. Save current Wi-Fi credentials
    2. Stop wpa_supplicant (client mode)
    3. Configure and start hostapd (AP mode)
    4. Start dnsmasq (DHCP server)
    5. When done: stop AP services, restore client mode
    """

    # Configuration file paths
    WPA_SUPPLICANT_CONF = "/etc/wpa_supplicant/wpa_supplicant.conf"
    HOSTAPD_CONF = "/tmp/hostapd_stream.conf"
    DNSMASQ_CONF = "/tmp/dnsmasq_stream.conf"
    WIFI_BACKUP_FILE = "/tmp/wifi_backup.conf"

    def __init__(self):
        self.state = APState.CLIENT_MODE
        self.saved_credentials: Optional[WiFiCredentials] = None
        self.ap_password: str = ""
        self._ap_ssid = settings.STREAM_AP_SSID
        self._ap_ip = settings.STREAM_AP_IP
        self._ap_netmask = settings.STREAM_AP_NETMASK
        self._ap_channel = settings.STREAM_AP_CHANNEL
        self._dhcp_start = settings.STREAM_DHCP_START
        self._dhcp_end = settings.STREAM_DHCP_END

    @property
    def ap_ssid(self) -> str:
        return self._ap_ssid

    @property
    def ap_ip(self) -> str:
        return self._ap_ip

    def _generate_password(self, length: int = 8) -> str:
        """Generate a random AP password"""
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))

    def _run_command(self, cmd: str, check: bool = True) -> Tuple[bool, str]:
        """Run a shell command and return success status and output"""
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            if check and result.returncode != 0:
                logger.error(f"Command failed: {cmd}")
                logger.error(f"stderr: {result.stderr}")
                return False, result.stderr
            return True, result.stdout
        except subprocess.TimeoutExpired:
            logger.error(f"Command timed out: {cmd}")
            return False, "Command timed out"
        except Exception as e:
            logger.error(f"Command error: {cmd} - {e}")
            return False, str(e)

    async def _run_command_async(self, cmd: str, check: bool = True) -> Tuple[bool, str]:
        """Run a shell command asynchronously"""
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

            if check and proc.returncode != 0:
                logger.error(f"Command failed: {cmd}")
                logger.error(f"stderr: {stderr.decode()}")
                return False, stderr.decode()
            return True, stdout.decode()
        except asyncio.TimeoutError:
            logger.error(f"Command timed out: {cmd}")
            return False, "Command timed out"
        except Exception as e:
            logger.error(f"Command error: {cmd} - {e}")
            return False, str(e)

    def save_wifi_credentials(self) -> bool:
        """
        Save current Wi-Fi credentials from wpa_supplicant.conf

        Returns:
            bool: True if credentials saved successfully
        """
        try:
            if not os.path.exists(self.WPA_SUPPLICANT_CONF):
                logger.warning("wpa_supplicant.conf not found, assuming no Wi-Fi configured")
                return True

            with open(self.WPA_SUPPLICANT_CONF, 'r') as f:
                content = f.read()

            # Parse the current network block
            # Look for: network={ ssid="..." psk="..." }
            ssid_match = re.search(r'ssid="([^"]+)"', content)
            psk_match = re.search(r'psk="([^"]+)"', content)

            if ssid_match:
                ssid = ssid_match.group(1)
                password = psk_match.group(1) if psk_match else ""

                self.saved_credentials = WiFiCredentials(
                    ssid=ssid,
                    password=password
                )

                # Also save a backup file
                with open(self.WIFI_BACKUP_FILE, 'w') as f:
                    f.write(f"ssid={ssid}\n")
                    f.write(f"password={password}\n")

                logger.info(f"Saved Wi-Fi credentials for network: {ssid}")
                return True
            else:
                logger.warning("No network configuration found in wpa_supplicant.conf")
                return True

        except Exception as e:
            logger.error(f"Failed to save Wi-Fi credentials: {e}")
            return False

    def _create_hostapd_config(self) -> bool:
        """Create hostapd configuration file"""
        try:
            # Generate password if not provided
            if settings.STREAM_AP_PASSWORD:
                self.ap_password = settings.STREAM_AP_PASSWORD
            else:
                self.ap_password = self._generate_password()

            config = f"""# Hostapd configuration for Calm Orb Live Streaming
interface=wlan0
driver=nl80211
ssid={self._ap_ssid}
hw_mode=g
channel={self._ap_channel}
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase={self.ap_password}
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
"""

            with open(self.HOSTAPD_CONF, 'w') as f:
                f.write(config)

            logger.info(f"Created hostapd config: SSID={self._ap_ssid}, Channel={self._ap_channel}")
            return True

        except Exception as e:
            logger.error(f"Failed to create hostapd config: {e}")
            return False

    def _create_dnsmasq_config(self) -> bool:
        """Create dnsmasq (DHCP) configuration file"""
        try:
            config = f"""# Dnsmasq configuration for Calm Orb Live Streaming
interface=wlan0
dhcp-range={self._dhcp_start},{self._dhcp_end},{self._ap_netmask},24h

# Redirect all DNS queries to Pi (captive portal style)
address=/#/{self._ap_ip}

# Specific entries for connectivity checks (makes phones think internet works)
address=/connectivitycheck.gstatic.com/{self._ap_ip}
address=/www.gstatic.com/{self._ap_ip}
address=/captive.apple.com/{self._ap_ip}
address=/www.apple.com/{self._ap_ip}
address=/clients3.google.com/{self._ap_ip}
address=/play.googleapis.com/{self._ap_ip}

# Disable upstream DNS (we're not routing to internet)
no-resolv
no-poll
"""

            with open(self.DNSMASQ_CONF, 'w') as f:
                f.write(config)

            logger.info(f"Created dnsmasq config: DHCP range {self._dhcp_start}-{self._dhcp_end}")
            return True

        except Exception as e:
            logger.error(f"Failed to create dnsmasq config: {e}")
            return False

    async def start_ap(self) -> bool:
        """
        Switch wlan0 to Access Point mode.
        wlan1 stays connected to ESP32.

        Returns:
            bool: True if AP started successfully
        """
        if self.state == APState.AP_READY:
            logger.info("AP already running")
            return True

        self.state = APState.AP_STARTING
        logger.info("Starting Access Point mode on wlan0...")

        try:
            # Step 1: Create configuration files
            if not self._create_hostapd_config():
                raise Exception("Failed to create hostapd config")

            if not self._create_dnsmasq_config():
                raise Exception("Failed to create dnsmasq config")

            # Step 2: Tell NetworkManager to release wlan0
            logger.info("Disabling NetworkManager on wlan0...")
            await self._run_command_async("sudo nmcli device set wlan0 managed no")
            await asyncio.sleep(2)

            # Step 3: Stop wpa_supplicant (client mode)
            logger.info("Stopping wpa_supplicant...")
            await self._run_command_async("sudo systemctl stop wpa_supplicant", check=False)
            await self._run_command_async("sudo killall wpa_supplicant", check=False)
            await asyncio.sleep(1)

            # Step 4: Kill any existing hostapd/dnsmasq
            await self._run_command_async("sudo killall hostapd", check=False)
            await self._run_command_async("sudo killall dnsmasq", check=False)
            await asyncio.sleep(0.5)

            # Step 5: Configure static IP on wlan0
            logger.info(f"Configuring static IP: {self._ap_ip}")
            await self._run_command_async("sudo ip addr flush dev wlan0")
            await self._run_command_async(f"sudo ip addr add {self._ap_ip}/24 dev wlan0")
            await self._run_command_async("sudo ip link set wlan0 up")
            await asyncio.sleep(0.5)

            # Step 6: Start hostapd
            logger.info("Starting hostapd...")
            success, output = await self._run_command_async(
                f"sudo hostapd -B {self.HOSTAPD_CONF}"
            )
            if not success:
                raise Exception(f"Failed to start hostapd: {output}")
            await asyncio.sleep(2)

            # Step 7: Start dnsmasq
            logger.info("Starting dnsmasq...")
            success, output = await self._run_command_async(
                f"sudo dnsmasq -C {self.DNSMASQ_CONF}"
            )
            if not success:
                raise Exception(f"Failed to start dnsmasq: {output}")
            await asyncio.sleep(1)

            # Verify AP is running
            success, output = await self._run_command_async("pgrep hostapd", check=False)
            if not success or not output.strip():
                raise Exception("hostapd is not running")

            self.state = APState.AP_READY
            logger.info(f"Access Point started successfully!")
            logger.info(f"  SSID: {self._ap_ssid}")
            logger.info(f"  Password: {self.ap_password}")
            logger.info(f"  IP: {self._ap_ip}")
            return True

        except Exception as e:
            logger.error(f"Failed to start AP: {e}")
            self.state = APState.AP_FAILED
            # Try to restore client mode on failure
            await self.restore_wifi()
            return False

    async def stop_ap(self) -> bool:
        """
        Stop Access Point mode.

        Returns:
            bool: True if AP stopped successfully
        """
        if self.state == APState.CLIENT_MODE:
            logger.info("Already in client mode")
            return True

        self.state = APState.AP_STOPPING
        logger.info("Stopping Access Point mode...")

        try:
            # Stop hostapd
            logger.info("Stopping hostapd...")
            await self._run_command_async("sudo killall hostapd", check=False)

            # Stop dnsmasq
            logger.info("Stopping dnsmasq...")
            await self._run_command_async("sudo killall dnsmasq", check=False)

            # Wait for processes to terminate
            await asyncio.sleep(1)

            # Clean up config files
            for conf_file in [self.HOSTAPD_CONF, self.DNSMASQ_CONF]:
                if os.path.exists(conf_file):
                    os.remove(conf_file)

            logger.info("Access Point stopped")
            return True

        except Exception as e:
            logger.error(f"Error stopping AP: {e}")
            return False

    async def restore_wifi(self) -> bool:
        """
        Restore original Wi-Fi client connection on wlan0.
        wlan1 stays connected to ESP32 (unaffected).

        Returns:
            bool: True if Wi-Fi restored successfully
        """
        logger.info("Restoring Wi-Fi client mode on wlan0...")

        retries = settings.STREAM_WIFI_RESTORE_RETRIES

        for attempt in range(retries):
            try:
                # Re-enable NetworkManager on wlan0
                logger.info("Re-enabling NetworkManager on wlan0...")
                await self._run_command_async("sudo nmcli device set wlan0 managed yes", check=False)
                await asyncio.sleep(1)

                # Flush IP configuration
                await self._run_command_async("sudo ip addr flush dev wlan0", check=False)
                await asyncio.sleep(0.5)

                # Restart wpa_supplicant
                logger.info("Starting wpa_supplicant...")
                await self._run_command_async("sudo systemctl start wpa_supplicant")
                await asyncio.sleep(2)

                # Request DHCP lease
                logger.info("Requesting DHCP lease...")
                await self._run_command_async("sudo dhclient wlan0", check=False)
                await asyncio.sleep(3)

                # Verify connectivity
                success, output = await self._run_command_async(
                    "ip addr show wlan0 | grep 'inet '",
                    check=False
                )

                if success and output.strip():
                    logger.info(f"Wi-Fi restored successfully: {output.strip()}")
                    self.state = APState.CLIENT_MODE
                    return True

                logger.warning(f"Wi-Fi restore attempt {attempt + 1}/{retries} failed")
                await asyncio.sleep(2)

            except Exception as e:
                logger.error(f"Wi-Fi restore attempt {attempt + 1} error: {e}")

        # Final fallback: reboot the wlan0 interface
        logger.warning("All restore attempts failed, rebooting wlan0 interface...")
        try:
            await self._run_command_async("sudo ip link set wlan0 down")
            await asyncio.sleep(1)
            await self._run_command_async("sudo ip link set wlan0 up")
            await asyncio.sleep(1)
            await self._run_command_async("sudo systemctl restart wpa_supplicant")
            await asyncio.sleep(3)
            await self._run_command_async("sudo dhclient wlan0", check=False)
            await asyncio.sleep(3)

            self.state = APState.CLIENT_MODE
            logger.info("Wi-Fi interface rebooted")
            return True

        except Exception as e:
            logger.error(f"Failed to reboot wlan0: {e}")
            self.state = APState.AP_FAILED
            return False

    def get_ap_credentials(self) -> dict:
        """
        Get AP credentials for mobile app.

        Returns:
            dict: AP credentials including SSID, password, and IP
        """
        return {
            "ssid": self._ap_ssid,
            "password": self.ap_password,
            "ip": self._ap_ip,
            "videoUrl": f"http://{self._ap_ip}:{settings.STREAM_VIDEO_PORT}/video",
            "audioUrl": f"ws://{self._ap_ip}:{settings.STREAM_AUDIO_PORT}",
        }

    def is_ap_active(self) -> bool:
        """Check if AP is currently active"""
        return self.state == APState.AP_READY

    def get_state(self) -> APState:
        """Get current AP state"""
        return self.state


# Test the module
if __name__ == "__main__":
    import asyncio

    logging.basicConfig(level=logging.INFO)

    async def test_ap():
        manager = APManager()

        # Save Wi-Fi credentials
        print("Saving Wi-Fi credentials...")
        manager.save_wifi_credentials()

        # Start AP
        print("\nStarting AP mode...")
        success = await manager.start_ap()

        if success:
            print(f"\nAP Credentials: {manager.get_ap_credentials()}")
            print("\nAP running for 30 seconds...")
            await asyncio.sleep(30)

        # Stop AP and restore Wi-Fi
        print("\nStopping AP and restoring Wi-Fi...")
        await manager.stop_ap()
        await manager.restore_wifi()

        print("\nTest complete!")

    asyncio.run(test_ap())
