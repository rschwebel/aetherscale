#!/usr/bin/env bash

apt update
apt -y install gnupg2 nginx-full apt-transport-https
apt-add-repository universe
apt update
apt -y install openjdk-8-jdk

hostnamectl set-hostname $JITSI_HOSTNAME

curl https://download.jitsi.org/jitsi-key.gpg.key | sudo sh -c 'gpg --dearmor > /usr/share/keyrings/jitsi-keyring.gpg'
echo 'deb [signed-by=/usr/share/keyrings/jitsi-keyring.gpg] https://download.jitsi.org stable/' | sudo tee /etc/apt/sources.list.d/jitsi-stable.list > /dev/null
apt update

echo "jitsi-videobridge jitsi-videobridge/jvb-hostname string $JITSI_HOSTNAME" | debconf-set-selections
echo "jitsi-meet jitsi-meet/cert-choice select Self-signed certificate will be generated" | debconf-set-selections
export DEBIAN_FRONTEND=noninteractive
apt -y install jitsi-meet
