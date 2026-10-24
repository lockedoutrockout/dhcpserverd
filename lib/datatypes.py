"""
lib/datatypes.py

Custom datatype definitions
"""

import os
import sys
import signal
import subprocess
import threading
from . import exceptions

"""
DHCP Lease Dictionary Structure

lease = {
    "id": 1, # Unique identifier for the lease
    "category": "dynamic", # Type of lease. Can be 'dynamic' or 'static'
    "mac_addr": "AA:BB:CC:DD:EE:FF", # MAC address
    "ip_addr": "192.168.0.10", # IP address
    "hostname": "some.device" # Hostname
}
"""

class DHCPLeaseList(object):
    """ DHCP lease list object
    """
    def __init__(self, settings, config=None, logger=None):
        self.config = config
        self.logger = logger
        self.settings = settings
        self.leases = {
            "all": [],
            "by_category": {
                "dynamic": [],
                "static": []
            }
        }

    def search_leases(self, query, category="any", search_param="id"):
        """ Search leases
        """
        if category == "any":
            target = self.leases["all"]
        elif category == "dynamic":
            target = self.leases["by_category"]["dynamic"]
        elif category == "static":
            target = self.leases["by_category"]["static"]

        for item in target:
            if search_param == "id":
                if int(query) == item["id"]:
                    return item
            elif search_param == "mac_addr":
                if query == item["mac_addr"]:
                    return item
            elif search_param == "ip_addr":
                if query == item["ip_addr"]:
                    return item
            elif search_param == "hostname":
                if query == item["hostname"]:
                    return item

        return None

    def add_lease(self, category, mac_addr, ip_addr, hostname):
        """ Add a new DHCP lease
        """
        if category not in ("dynamic", "static"):
            raise exceptions.DHCPLeaseListError(f"Invalid category: {category}")
        if category == "dynamic":
            if self.search_leases(mac_addr, category="dynamic", search_param="mac_addr"):
                raise exceptions.DHCPLeaseListError(f"A dynamic DHCP lease already exists for MAC address: {mac_addr}")
        else:
            if self.search_leases(mac_addr, category="static", search_param="mac_addr"):
                raise exceptions.DHCPLeaseListError(f"A static DHCP lease already exists for MAC address: {mac_addr}")
            
            
        id_ = len(self.leases["all"]) + 1
        while self.search_leases(id_, category="any", search_param="id") is not None:
            id_ += 1
        lease = {
            "id": id_,
            "category": category,
            "mac_addr": mac_addr,
            "ip_addr": ip_addr,
            "hostname": hostname
        }
        if category == "static":
            ip_collision = self.search_leases(ip_addr, category="static", search_param="ip_addr")
            if ip_collision:
                raise exceptions.DHCPLeaseListError(f"Cannot create static lease! IP address already assigned: {ip_addr}")
            dynamic = self.search_leases(mac_addr, category="dynamic", search_param="mac_addr")
            if dynamic:
                self.remove_lease(dynamic["id"])
        self.leases["all"].append(lease)
        self.leases["by_category"][lease["category"]].append(lease)
        return id_

    def remove_lease(self, id_):
        """ Remove an existing DHCP lease
        """
        if not self.search_leases(id_, category="any", search_param="id"):
            raise exceptions.DNSLeaseListError(f"No lease exists with an ID of: {id_}")
        lease = self.search_leases(id_, category="any", search_param="id")
        self.leases["all"].remove(lease)
        self.leases["by_category"][lease["category"]].remove(lease)
        return lease
        

class DHCPServer(object):
    """ DHCP server backend
    """
    def __init__(self, config=None, logger=None):
        self.config = config
        self.logger = logger
        self.processes = {}
        self.state = "not running"
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
        self.dhcp_leases = DHCPLeaseList(self.settings, config=self.config, logger=self.logger)
        

    def _gen_dnsmasq_config(self, outfile):
        """ Generate the dnsmasq configuration file
        """
        settings = []
        for setting in [
            f"interface={self.config['HARDWARE']['interface']}",
            f"bind-interfaces",
            f"dhcp-range={self.settings['IPLeasePool'][0]},{self.settings['IPLeasePool'][1]},{self.settings['IPLeaseDuration']}",
            f"port=0",
            f"dhcp-option=3,{self.settings['GatewayIP']}",
            f"dhcp-option=6,{self.settings['DNSServerIP']}",
            f"log-dhcp",
            f"dhcp-leasefile={self.config['DNSMASQ']['leases_file']}",
            f"dhcp-hostsfile={self.config['DNSMASQ']['hosts_file']}",
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
        for lease in self.dhcp_leases.leases["by_category"]["static"]:
            entries.append(f"{lease["mac_addr"]},{lease["ip_addr"]},{lease["hostname"]},infinite")

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
            self._gen_dnsmasq_config(self.config["DNSMASQ"]["config_file"])
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

    def _AddStaticLease(self, mac_addr, ip_addr, hostname):
        """ Add a static lease
        """
        try:
            id_ = self.dhcp_leases.add_lease("static", mac_addr, ip_addr, hostname)
            self._gen_hosts_file()
            self._reload_dnsmasq()
        except Exception as err_msg:
            raise err_msg
        return id_

    def _RemoveStaticLease(self, id_):
        """ Remove a static lease
        """
        try:
            lease = self.dhcp_leases.remove_lease(id_)
            self._gen_hosts_file()
            self._reload_dnsmasq()
        except Exception as err_msg:
            raise err_msg
        return lease

    def _EventScriptCallback(self, action, mac_addr, ip_addr, hostname):
        """ Event script callback logic
        """
        if action in ("add", "add6"):
            try:
                id_ = self.dhcp_leases.add_lease("dynamic", mac_addr, ip_addr, hostname)
                return ("lease established", self.dhcp_leases.search_leases(id_, category="any", search_param="id"))
            except Exception as err_msg:
                raise err_msg
        if action in ("old", "old6"):
            try:
                return ("lease renewed", self.dhcp_leases.search_leases(mac_addr, category="any", search_param="mac_addr"))
            except Exception as err_msg:
                raise err_msg
        if action in ("del", "del6"):
            try:
                lease = self.dhcp_leases.search_leases(mac_addr, category="any", search_param="mac_addr")
                self.dhcp_leases.remove_lease(lease["id"])
                return ("lease expired", lease)
            except Exception as err_msg:
                raise err_msg
