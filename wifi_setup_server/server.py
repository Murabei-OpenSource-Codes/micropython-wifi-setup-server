"""
Class to configure internet access.

It uses an acess point to config credentials.
"""
import os
import socket
import network
import machine
import ubinascii
import json
import time


class WifiSetupServer:
    """Class to connect to internet."""

    WIFI_CONFIG_FILE = "./config/wifi_credentials.json"
    local_path = "lib/wifi_setup_server"
    wifi_ok = False
    sta_if = network.WLAN(network.STA_IF)
    ap_if = network.WLAN(network.AP_IF)

    def __init__(self, config_server_pin: machine.Pin = None,
                 connecting_wifi_pin: machine.Pin = None,
                 connected_wifi_pin: machine.Pin = None,
                 access_point_password: str = "password"):
        """
        __init__.

        Args:
            config_server_pin [machine.Pin]: Pin to be set on if config server
                is avaiable.
            connecting_wifi_pin [machine.Pin]: Pin to be set on if board is
                conneting to WiFi.
            connected_wifi_pin [machine.Pin]: Pin to be set on if board is
                connected to WiFi.
        """
        # Create socket to get requests from server
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self._socket.bind(('', 80))
            self._socket.listen(5)
        except Exception:
            print("# Port 80 already on listen #")

        # Save indicator pins
        self._config_server_pin = config_server_pin
        self._connecting_wifi_pin = connecting_wifi_pin
        self._connected_wifi_pin = connected_wifi_pin
        self._access_point_password = access_point_password

        # blank all light pins
        self.light_pin(message="all_off")

    def light_pin(self, message: str) -> None:
        """
        Light board status PIN to indicate internet connection.

        Args:
            message [str]: Message of the pin to light. To work it must be in
                [config_server, connecting_wifi, connected_wifi]
        Return:
            None
        """
        if message == "config_server":
            if self._config_server_pin is not None:
                self._config_server_pin.on()
            if self._connecting_wifi_pin is not None:
                self._connecting_wifi_pin.off()
            if self._connected_wifi_pin is not None:
                self._connected_wifi_pin.off()

        elif message == "connecting_wifi":
            if self._config_server_pin is not None:
                self._config_server_pin.off()
            if self._connecting_wifi_pin is not None:
                self._connecting_wifi_pin.on()
            if self._connected_wifi_pin is not None:
                self._connected_wifi_pin.off()

        elif message == "connected_wifi":
            if self._config_server_pin is not None:
                self._config_server_pin.off()
            if self._connecting_wifi_pin is not None:
                self._connecting_wifi_pin.off()
            if self._connected_wifi_pin is not None:
                self._connected_wifi_pin.on()

        else:
            if self._config_server_pin is not None:
                self._config_server_pin.off()
            if self._connecting_wifi_pin is not None:
                self._connecting_wifi_pin.off()
            if self._connected_wifi_pin is not None:
                self._connected_wifi_pin.off()

    def get_board_id(self) -> str:
        """
        Return board indentification id.

        Args:
            No Args.
        Return:
            Return board indentification id.
        """
        machine_id_bytes = machine.unique_id()
        machine_id = ubinascii.hexlify(machine_id_bytes).decode('utf-8')
        return machine_id

    def scan_avaiable_wifi(self) -> list:
        """
        Scan avaiable WiFi networks.

        Args:
            No args.
        Return [list]:
            Return a list of avaiable Wifi networks to connect.
        """
        # Activate the Wi-Fi interface
        self.sta_if.active(True)
        list_avaiable_wifi = self.sta_if.scan()
        list_return_wifi = []
        for r in list_avaiable_wifi:
            list_return_wifi.append(r[0].decode('utf-8'))
        list_return_wifi.sort()
        return list_return_wifi

    def start_configuration_ap(self) -> bool:
        """
        Connect to internet.

        It set password and user as a file if connection is successful.

        Args:
            password [str]: Wifi connection password.
        """
        print("# start_configuration_ap")
        # Activate the Wi-Fi interface
        self.sta_if.active(False)
        self.ap_if.active(True)
        machine_id = self.get_board_id()

        # Configure the access point
        self.ap_if.config(
            essid="ESP32 %s" % (machine_id, ),
            password=self._access_point_password,
            authmode=network.AUTH_WPA_WPA2_PSK)

        # Print the IP address of the access point
        print("# Access Point IP address:", self.ap_if.ifconfig()[0])
        return True

    def parse_post_json(self, request_data) -> dict:
        """
        Parse POST requests from ESP32 web server.

        Args:
            request: Micropython socket data.
        Return [dict]:
            Post request data payload.
        """
        try:
            return json.loads(request_data)
        except Exception:
            raise Exception("Invalid JSON data")

    def serve_config_page(self) -> dict:
        """
        Serve config page.

        Args:
            No Args.
        Return [dict]:
            Return wifi credentials with ssid and password keys.
        """
        # Scanning ports for wifi
        avaiable_wifi = self.scan_avaiable_wifi()

        # Light indicator light
        self.light_pin(message="config_server")

        # Start access point
        self.start_configuration_ap()

        ################################################
        # Build configuration page for WiFi connection #
        file_path = "{local_path}/server/html/configure_wifi.html".format(
            local_path=self.local_path)
        with open(file_path) as file:
            temp_page_content = file.read()

        file_path = (
            "{local_path}/server/html/configure_wifi_options.html").format(
            local_path=self.local_path)
        with open(file_path) as file:
            wifi_options_fmt = file.read()

        # Create options using avaialbe WiFi networks for ESP Board
        wifi_options = "\n".join(
            [wifi_options_fmt.format(ssid=x) for x in avaiable_wifi])
        page_content = temp_page_content.replace(
            "[[wifi_options]]", wifi_options)

        ################################################
        # Serve configuration page and listen requests #
        print("# Serving Config page")
        parsed_data = None
        while True:
            conn, addr = self._socket.accept()  # Accept a client connection
            print('Got a connection from %s' % str(addr))

            request = conn.recv(1024).decode('utf-8')
            method, path, version = request.split('\r\n')[0].split()
            headers = request.split('\r\n\r\n')[0].split('\r\n')[1:]
            request_data = request.split('\r\n\r\n')[1]
            if "POST" in method:
                parsed_data = self.parse_post_json(request_data)
                if set(parsed_data.keys()) != {'ssid', 'password'}:
                    conn.send('HTTP/1.1 400 OK\n')
                    conn.send('Content-Type: application/json\n')
                    conn.send('Connection: close\n\n')
                    conn.sendall(json.dumps({
                        "error": (
                            "Dictionary must have 'ssid', 'password' keys")
                    }))
                    conn.close()

                conn.send('HTTP/1.1 200 OK\n')
                conn.send('Content-Type: application/json\n')
                conn.send('Connection: close\n\n')
                conn.sendall(json.dumps({
                    "status": "OK"
                }))
                conn.close()

                # Return credentials
                return parsed_data
            else:
                conn.send('HTTP/1.1 200 OK\n')
                conn.send('Content-Type: text/html\n')
                conn.send('Connection: close\n\n')
                conn.sendall(page_content)
                conn.close()

    def connect_wifi(self, ssid: str, password: str) -> bool:
        """
        Connect to wifi.

        Args:
            ssid [str]: Wiffi ssid.
            password [str]: Wiffi password.

        Return:
            Bollean indicating if connection was successful.
        """
        # Light indicator light
        self.light_pin(message="connecting_wifi")

        self.ap_if.active(False)
        self.sta_if.active(True)
        self.sta_if.connect(ssid, password)
        for i in range(30):
            print('# Waiting connection for %s seconds' % i)
            if self.sta_if.isconnected():
                str_wiffi_credentials = json.dumps({
                    "ssid": ssid, "password": password})
                with open(self.WIFI_CONFIG_FILE, "w") as file:
                    file.write(str_wiffi_credentials)
                return True
            time.sleep(1)
        else:
            return False

    def is_wifi_ok(self) -> bool:
        """
        Return a boolean indicating if wifi is ok.

        Args:
            No args.

        Kwargs:
            No kwargs.

        Return [bool]:
            Return a boolean indicating if wifi is ok
        """
        if self.sta_if.isconnected():
            self.light_pin(message="connected_wifi")
            return True
        else:
            self.light_pin(message="all_off")
            return False

    def configure_wifi(self):
        """
        Connect to wifi.

        Try to connect using previous WiFi credentials, if not possible
        will open a acess point to configure WiFi connection.

        Args:
            No Args.

        Kwargs:
            No Kwargs.

        Return:
            No Return.
        """
        while not self.is_wifi_ok():
            config_files = os.listdir("./config")
            if 'wifi_credentials.json' in config_files:
                with open('./config/wifi_credentials.json', "r") as file:
                    credentials = json.loads(file.read())
                print("# Credentials found, tring to connect:")
                connected = self.connect_wifi(
                    ssid=credentials['ssid'],
                    password=credentials['password'])
                if not connected:
                    print("# Credentials not valid removing credentials file:")
                    os.remove('./config/wifi_credentials.json')
            else:
                credentials = self.serve_config_page()
                connected = self.connect_wifi(
                    ssid=credentials['ssid'],
                    password=credentials['password'])
