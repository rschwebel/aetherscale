#!/usr/bin/env bash

MOUNT=/tmp/mount

mkdir $MOUNT

guestmount -a jitsi2.qcow2 -i $MOUNT
cp jitsi-install.sh $MOUNT/root
cp jitsi-install.service $MOUNT/etc/systemd/system/
ln -s /etc/systemd/system/jitsi-install.service $MOUNT/etc/systemd/system/multi-user.target.wants/
guestunmount $MOUNT
