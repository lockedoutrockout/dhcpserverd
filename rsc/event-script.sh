#!/bin/sh

###########################################################################################
# rsc/event-script.sh                                                                     #
#                                                                                         #
# Called by dnsmasq when DHCP related events occur. Used to pass these events from        #
# dnsmasq to the dhcpserverd daemon via the daemon's DBus interface's EventScriptCallback #
# method                                                                                  #
###########################################################################################

ACTION="$1"
MAC_ADDR="$2"
IP_ADDR="$3"
HOSTNAME="$4"

dbus-send --system \
    --dest=com.dhcpserverd.DHCPServer \
    /com/dhcpserverd/DHCPServer \
    com.dhcpserverd.DHCPServer.EventScriptCallback \
    string:"$ACTION" string:"$MAC_ADDR" string:"$IP_ADDR" string:"$HOSTNAME"
