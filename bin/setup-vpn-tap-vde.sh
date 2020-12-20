#!/usr/bin/env bash

usage() {
    echo "Usage: $0 -u USER -n NUM-DEVICES -p IPv6-48-PREFIX"
}

while getopts ":hu:n:p:" opt; do
    case "$opt" in
    h|\?)
        usage
        exit 0
        ;;
    u)  user=$OPTARG
        ;;
    n)  num_devices=$OPTARG
        ;;
    p)  prefix=$OPTARG
        ;;
    esac
done

if [[ -z $user || -z $num_devices || -z $prefix]]; then
    usage
    echo
    echo "Please specify all required arguments"
    exit 1
fi

for i in $(seq 1 $num_devices); do
    bridge_name=aeth-vpnbr-$i
    tinc_name=aeth-vpntnc-$i
    vde_name=aeth-vpnvde-$i

    ip link add $bridge_name type bridge
    ip link set $bridge_name up

    ip tuntap add dev $tinc_name mode tap user $user
    ip link set $tinc_name up
    ip link set $tinc_name master $bridge_name
    ip addr flush dev $tinc_name

    ip tuntap add dev $vde_name mode tap user $user
    ip link set dev $vde_name up
    ip link set $vde_name master $bridge_name

    ip addr add $prefix:$i::1/64 dev $bridge_name
done
