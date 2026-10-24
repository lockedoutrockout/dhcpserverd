"""
lib/api.py

Contains the DBus interface
"""

import os
import sys
import logging
import configparser
from pydbus import SystemBus
from pydbus.generic import signal
from gi.repository import GLib
from . import (
    datatypes,
    exceptions
)

BUS_NAME = "com.dhcpserverd.DHCPServer"
OBJECT_PATH = "/com/dhcpserverd/DHCPServer"
INTERFACE_XML = """
<node>
    <interface name="com.dhcpserverd.DHCPServer">
        <!-- Methods -->
        <method name="Start"/>
        <method name="Stop"/>
        <method name="Restart"/>
        <method name="ApplyConfiguration"/>
        <method name="AddStaticLease">
            <arg type="s" name="mac_addr" direction="in"/>
            <arg type="s" name="ip_addr" direction="in"/>
            <arg type="i" name="id" direction="out"/>
        </method>
        <method name="RemoveStaticLease">
            <arg type="i" name="id" direction="in"/>
        </method>
        <method name="EventScriptCallback">
            <arg type="s" name="action" direction="in"/>
            <arg type="s" name="mac_addr" direction="in"/>
            <arg type="s" name="ip_addr" direction="in"/>
            <arg type="s" name="hostname" direction="in"/>
        </method>

        <!-- Properties -->
        <!-- Read Only -->
        <property name="State" type="s" access="read"/>
        <property name="Leases" type="aa{sv}" access="read"/>
        <property name="DynamicLeases" type="aa{sv}" access="read"/>
        <property name="StaticLeases" type="aa{sv}" access="read"/>
        <!-- Read/Write -->
        <property name="IPLeasePool" type="as" access="readwrite"/>
        <property name="IPLeaseDuration" type="s" access="readwrite"/>
        <property name="GatewayIP" type="s" access="readwrite"/>
        <property name="DNSServerIP" type="s" access="readwrite"/>

        <!-- Signals -->
        <signal name="StateChanged">
            <arg type="s" name="old_state"/>
            <arg type="s" name="new_state"/>
        </signal>
        <signal name="ConfigurationChanged">
            <arg type="s" name="setting"/>
            <arg type="s" name="old_value"/>
            <arg type="s" name="new_value"/>
        </signal>
        <signal name="ConfigurationApplied">
            <arg type="a{sv}" name="old_config"/>
            <arg type="a{sv}" name="new_config"/>
        </signal>
        <signal name="DHCPLeaseEvent">
            <arg type="s" name="event_type"/>
            <arg type="a{sv}" name="lease"/>
        </signal>
    </interface>
</node>
"""

def dict_to_dbus_asv(d):
    """ Sanatizes a dictionary for use as an array of string variants in DBus
    """
    for k in d.keys():
        s = str(d[k])
        d[k] = s
    return d

class DHCPServerService(datatypes.DHCPServer):
    """ DBus interface object
    """

    # Signals
    StateChanged = signal()
    ConfigurationChanged = signal()
    ConfigurationApplied = signal()
    DHCPLeaseEvent = signal()

    def __init__(self):
        self.version = "0.1"
        config = configparser.ConfigParser()
        config.read(sys.argv[1:])
        logger = logging.getLogger()
        super().__init__(config=config, logger=logger)

    # Methods
    def Start(self):
        """ Start endpoint
        """
        self.logger.info(f"DBus API got call to Start")
        try:
            _old = self.state
            self._Start()
            self.StateChanged(_old, self.state)
        except Exception as err_msg:
            self.logger.error(f"DBus API encountered an exception during call to Start: {err_msg}")
            raise exceptions.StateChangeError(f"An error has prevented the template from starting") from err_msg
        return None

    def Stop(self):
        """ Stop endpoint
        """
        self.logger.info(f"DBus API got call to Stop")
        try:
            _old = self.state
            self._Stop()
            self.StateChanged(_old, self.state)
        except Exception as err_msg:
            self.logger.error(f"DBus API encountered an exception during call to Stop: {err_msg}")
            raise exceptions.StateChangeError(f"An error has prevented the AP host from stopping") from err_msg
        return None

    def Restart(self):
        """ Restart endpoint
        """
        self.logger.info(f"DBus API got call to Restart")
        try:
            _old = self.state
            self._Restart()
            self.StateChanged(_old, self.state)
        except Exception as err_msg:
            self.logger.error(f"DBus API encountered an exception during call to Restart: {err_msg}")
            raise exceptions.StateChangeError(f"An error has prevented the AP host from restarting") from err_msg
        return None

    def ApplyConfiguration(self):
        """ Apply endpoint
        """
        self.logger.info(f"DBus API got call to Apply")
        try:
            _old = dict_to_dbus_asv(self.settings)
            self._ApplyConfiguration()
            self.ConfigurationApplied(_old, dict_to_dbus_asv(self.settings))
        except Exception as err_msg:
            self.logger.error(f"DBus API encountered an exception during call to ApplyConfiguration: {err_msg}")
        return None

    def AddStaticLease(self, mac_addr, ip_addr, hostname):
        """ Add a static lease
        """
        self.logger.info(f"DBus API got call to AddStaticLease")
        try:
            id_ = self._AddStaticLease(mac_addr, ip_addr, hostname)
            self.DHCPLeaseEvent("lease established", self.dhcp_leases.search_leases(id_, category="static", search_param="id"))
        except Exception as err_msg:
            self.logger.error(f"DBus API encountered an exception during call to AddStaticLease: {err_msg}")
        return None

    def RemoveStaticLease(self, id_):
        """ Remove a static lease
        """
        self.logger.info(f"DBus API got call to RemoveStaticLease")
        try:
            lease = self._RemoveStaticLease(id_)
            self.DHCPLeaseEvent("lease expired", lease)
        except Exception as err_msg:
            self.logger.error(f"DBus API encountered an exception during call to RemoveStaticLease: {err_msg}")
        return None

    def EventScriptCallback(self, action, mac_addr, ip_addr, hostname):
        """ Callback method for DHCP event script
        """
        self.logger.info(f"DBus API got call to EventScriptCallback")
        try:
            event_type, lease = self._EventScriptCallback(action, mac_addr, ip_addr, hostname)
            self.DHCPLeaseEvent(event_type, lease)
        except Exception as err_msg:
            self.logger.error(f"DBus API encountered an exception during call to RemoveStaticLease: {err_msg}")
        return None
        

    # Properties
    @property
    def State(self):
        return self.state

    @property
    def Leases(self):
        return self.dhcp_leases.leases["all"]

    @property
    def DynamicLeases(self):
        return self.dhcp_leases.leases["by_category"]["dynamic"]

    @property
    def StaticLeases(self):
        return self.dhcp_leases.leases["by_category"]["static"]

    @property
    def IPLeasePool(self):
        return self.settings["IPLeasePool"]
    @IPLeasePool.setter
    def IPLeasePool(self, value):
        self.logger.info(f"Readwrite property IPLeasePool set to {value} from {self._settings['IPLeasePool']}")
        _old = self._settings["IPLeasePool"]
        try:
            self._settings["IPLeasePool"] = value
            self.ConfigurationChanged("IPLeasePool", _old, self._settings["IPLeasePool"])
        except Exception as err_msg:
            self.logger.error(f"DBus API encountered an exception while setting value of readwrite property IPLeasePool from: {_old} to: {value}")
            raise exceptions.ConfigurationError(f"Failed to update value of read/write property: IPLeasePool")

    @property
    def IPLeaseDuration(self):
        return self.settings["IPLeaseDuration"]
    @IPLeaseDuration.setter
    def IPLeaseDuration(self, value):
        self.logger.info(f"Readwrite property IPLeaseDuration set to {value} from {self._settings['IPLeaseDuration']}")
        _old = self._settings["IPLeaseDuration"]
        try:
            self._settings["IPLeaseDuration"] = value
            self.ConfigurationChanged("IPLeaseDuration", _old, self._settings["IPLeaseDuration"])
        except Exception as err_msg:
            self.logger.error(f"DBus API encountered an exception while setting value of readwrite property IPLeaseDuration from: {_old} to: {value}")
            raise exceptions.ConfigurationError(f"Failed to update value of read/write property: IPLeaseDuration")

    @property
    def GatewayIP(self):
        return self.settings["GatewayIP"]
    @GatewayIP.setter
    def GatewayIP(self, value):
        self.logger.info(f"Readwrite property GatewayIP set to {value} from {self._settings['GatewayIP']}")
        _old = self._settings["GatewayIP"]
        try:
            self._settings["GatewayIP"] = value
            self.ConfigurationChanged("GatewayIP", _old, self._settings["GatewayIP"])
        except Exception as err_msg:
            self.logger.error(f"DBus API encountered an exception while setting value of readwrite property GatewayIP from: {_old} to: {value}")
            raise exceptions.ConfigurationError(f"Failed to update value of read/write property: GatewayIP")

    @property
    def DNSServerIP(self):
        return self.settings["DNSServerIP"]
    @DNSServerIP.setter
    def DNSServerIP(self, value):
        self.logger.info(f"Readwrite property DNSServerIP set to {value} from {self._settings['DNSServerIP']}")
        _old = self._settings["DNSServerIP"]
        try:
            self._settings["DNSServerIP"] = value
            self.ConfigurationChanged("DNSServerIP", _old, self._settings["DNSServerIP"])
        except Exception as err_msg:
            self.logger.error(f"DBus API encountered an exception while setting value of readwrite property DNSServerIP from: {_old} to: {value}")
            raise exceptions.ConfigurationError(f"Failed to update value of read/write property: DNSServerIP")

def init_dbus_api(name=BUS_NAME, path=OBJECT_PATH, xml=INTERFACE_XML, logger=None):
    """ Launch the DBus interface
    """
    if logger:
        logger.info(f"Bringing up DBus API. Interface: {name} Path: {path}")
    bus = SystemBus()
    bus.publish(name, (path, DHCPServerService(), xml))
    GLib.MainLoop().run()
    return None
