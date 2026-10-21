"""
lib/datatypes.py

Custom datatype definitions
"""

import os
import sys
import signal
import subprocess
from . import exceptions

class DHCPServer(object):
    """ DHCP server backend
    """
    def __init__(self, config=None, logger=None):
        self.config = config
        self.logger = logger
        self.processes = {}
        self.state = "not running"
        self.leases = []
        self.dynamic_leases = []
        self.static_leases = []
        self.settings = {
            "IPLeasePool": (self.config["DHCP"]["ip_lease_pool_start"], self.config["DHCP"]["ip_lease_pool_end"]),
            "IPLeaseDuration": self.config["DHCP"]["ip_lease_duration"],
            "GatewayIP": self.config["DHCP"]["gateway_ip"],
            "DNSServerIP": self.config["DHCP"]["dns_server_ip"]
        }
        self._settings = {
            "IPLeasePool": (self.config["DHCP"]["ip_lease_pool_start"], self.config["DHCP"]["ip_lease_pool_end"]),
            "IPLeaseDuration": self.config["DHCP"]["ip_lease_duration"],
            "GatewayIP": self.config["DHCP"]["gateway_ip"],
            "DNSServerIP": self.config["DHCP"]["dns_server_ip"]
        }

    def _search_leases(self, query, lease_type="any", search_param="id"):
        """ Search leases
        """
        if lease_type == "any":
            target = self.leases
        elif lease_type == "dynamic":
            target = self.dynamic_leases
        elif lease_type == "static":
            target = self.static_leases

        for item in target:
            if search_param == "id":
                if int(query) == item[0]:
                    return item
            elif search_param == "mac_addr":
                elif query == item[1]:
                    return item
            elif search_param == "ip_addr":
                elif query == item[2]:
                    return item
            elif search_param == "hostname":
                elif query == item[3]:
                    return item

        return None

    def _gen_dnsmasq_config(self, outfile):
        """ Generate the dnsmasq configuration file
        """
        settings = []
        for setting in [
            f"interface={self.config['HARDWARE']['interface']}",
            f"bind-interfaces",
            f"dhcp-range={self.settings['IPLeasePool'][0]},{self.settings['IPLeasePool'][1]},{self.settings['IPLeaseDuration']}"
            f"port=0",
            f"dhcp-option=3,{self.settings['GatewayIP']}",
            f"dhcp-option=6,{self.settings['DNSServerIP']}",
            f"log-dhcp",
            f"dhcp-leasefile={self.config['DNSMASQ']['leases_file']}"
            f"dhcp-hostsfile={self.config['DNSMASQ']['hosts_file']}"
            f"dhcp-script=/etc/dhcpserverd/rsc/event-script.sh"
        ]:
            settings.append(setting)

        with open(outfile, "w") as fd:
            for setting in settings:
                fd.write(setting + "\n")

        return None

    def _gen_hosts_file(self):
        """ Generate the static lease entries for the dnsmasq config file
        """
        entries = []
        for lease in self.static_leases:
            hostname = lease[3] if lease[3] else ""
            entry = f"{lease[1]},{lease[2]},{hostname},infinite"
            entries.append(entry)

        with open(self.config["DNSMASQ"]["hosts_file"], "w") as fd:
            for entry in entries:
                fd.write(entry + "\n")

        return None

    def _reload_dnsmasq(self):
        """ Reload dnsmasq
        """
        try:
            os.kill(self.processes["dnsmasq"].pid, signal.SIGHUP)
        except Exception as err_msg:
            raise err_msg
        return None
        
    def _Start(self):
        """ Start the process
        """
        def _dnsmasq_runner(logger, config):
            """ Runner thread for dnsmasq
            """
            logger.info(f"Started dnsmasq runner thread")
            sublogger = logging.getLogger("dnsmasq_runner")
            slch = logging.StreamHandler()
            log_level = int(config["LOGGING"]["log_level"])
            if log_level == -1:
                log_level = logging.DEBUG
            elif log_level == 0:
                log_level = logging.INFO
            elif log_level == 1:
                log_level = logging.ERROR
            slch.setLevel(log_level)
            slch.setFormatter(logging.Formatter("%(name)s - %(message)s"))
            sublogger.addHandler(slch)
            sublogger.info(f"Sublogger initialized for dnsmasq subprocess")
            p = subprocess.Popen(
                [
                    self.config["DNSMASQ"]["executable"],
                    "-d",
                    "--log-debug",
                    "-C",
                    self.config["DNSMASQ"]["config_file"],
                    "--keep-in-foreground"
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            self.processes["dnsmasq"] = p
            for line in p.stdout:
                sublogger.info(line.rstrip())
            retcode = p.wait()
            if retcode != 0:
                logger.error(f"The dnsmasq subprocess has exited with a non-zero return code of: {retcode}")
            else:
                logger.info(f"The dnsmasq subprocess has exited")
            return None
            
        if self.state == "running":
            raise exceptions.StateChangeError(f"DHCP server is already running")
        try:
            self.state = "starting"
            self._gen_dnsmasq_config(self.config["HOSTAPD"]["config_file"])
            self._gen_hosts_file()
            threading.Thread(target=_dnsmasq_runner, args=(self.logger, self.config), daemon=True).start()
            time.sleep(0.5)
            if self.processes["dnsmasq"].returncode:
                raise exceptions.ChildProcessExitedError(f"dnsmasq exited with return code of: {self.processes['dnsmasq'].returncode}")
        except Exception as err_msg:
            self.state = "startup failed"
            raise err_msg
        self.state = "running"
        return None

    def _Stop(self):
        """ Stop the process
        """
        if self.state == "not running":
            raise exceptions.StateChangeError(f"DHCP server is not running")
        try:
            for process_name in self.processes.keys():
                self.logger.debug(f"Stopping subprocess: {process_name}")
                process = self.processes[process_name]
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                self.processes[process_name] = None
        except Exception as err_msg:
            self.state = "shutdown failed"
            raise err_msg
        self.state = "not running"
        return None

    def _Restart(self):
        """ Restart the process
        """
        if self.state == "not running":
            raise exceptions.StateChangeError(f"Process is not running")
        try:
            self._Stop()
            self._Start()
        except Exception as err_msg:
            self.state = "restart failed"
            raise err_msg
        return None

    def _ApplyConfiguration(self):
        """ Apply new configuration settings
        """
        self.settings = self._settings
        try:
            pass
        except Exception as err_msg:
            self.state = "apply configuration failed"
            raise err_msg
        return None

    def _AddStaticLease(self, mac_addr, ip_addr):
        """ Add a static lease
        """
        if self._search_leases(mac_addr, lease_type="static", search_param="mac_addr"):
            raise exceptions.LeaseError(f"A static lease for {mac_addr} already exists")
        try:
            id_ = len(self.leases) + 1
            while self._search_leases(query, lease_type="any", search_param="id"):
                id_ += 1
            existing = self._search_leases(mac_addr, lease_type="any", search_param="mac_addr")
            if existing:
                hostname = existing[3]
            else:
                hostname = None
            lease = (id_, mac_addr, ip_addr, hostname)

            dynamic = self._search_leases(mac_addr, lease_type="dynamic", search_param="mac_addr")
            if dynamic:
                self.dynamic_leases.remove(dynamic)
            self.leases.append(lease)
            self.static_leases.append(lease)

            self._gen_hosts_file()
            self._reload_dnsmasq()
        except Exception as err_msg:
            raise err_msg
        return id_

    def _RemoveStaticLease(self, id_):
        """ Remove a static lease
        """
        if not self._search_leases(id_, lease_type="static", search_param="id"):
            raise exceptions.LeaseError(f"A static lease for {id_} does not exist")
        try:
            self.static_leases.remove(self._search_leases(id_, lease_type="static", search_param="id"))
            self._gen_hosts_file()
            self._reload_dnsmasq()
        except Exception as err_msg:
            raise err_msg
        return None
