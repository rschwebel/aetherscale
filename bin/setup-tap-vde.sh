#!/usr/bin/env bash

usage() {
    echo "Usage: $0 -u USER -i IP_ADDRESS -g GATEWAY -e eth_device_DEVICE"
}

while getopts ":hu:i:g:e:" opt; do
    case "$opt" in
    h|\?)
        usage
        exit 0
        ;;
    u)  user=$OPTARG
        ;;
    i)  ip_address=$OPTARG
        ;;
    g)  gateway=$OPTARG
        ;;
    e)  eth_device=$OPTARG
        ;;
    esac
done

if [[ -z $user || -z $ip_address || -z $gateway || -z $eth_device ]]; then
    usage
    echo
    echo "Please specify all required arguments"
    exit 1
fi


VDE_TAP=tap-vde

ip link add br0 type bridge
ip link set br0 up

ip link set $eth_device up
ip link set $eth_device master br0

# Drop existing IP from eth0
ip addr flush dev $eth_device

# Assign IP to br0
ip addr add $ip_address brd + dev br0
ip route add default via $gateway dev br0

ip tuntap add dev $VDE_TAP mode tap user $user
ip link set dev $VDE_TAP up
ip link set $VDE_TAP master br0
