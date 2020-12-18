# aetherscale

aetherscale is small hobby project to create a hosting environment that can
be controlled via an HTTP API. I just want to have some fun and
dive deeper into Linux tooling (networking, virtualization and so on) and
into distributed applications. I do not think that this will become
production-ready at any point.

This is developed along with
[a blog tutorial series about scalable computing](https://blog.stefan-koch.name/2020/11/22/programming-cloud-hosting-python-rabbitmq-qemu)
which I am currently writing.

## Installation

You can install the package with:

```bash
git clone https://github.com/aufziehvogel/aetherscale
cd aetherscale
virtualenv venv && source venv/bin/activate
pip install -e .
```

Before you can start using the server you need to setup a TAP device to which
VDE networking can connect. This is needed so that the started VMs can
join the network. To be able to create a TAP device that is connected to your
real network, you might also have to setup a software bridge. aetherscale
includes a script to help you with this. Since I could only test on my PC
it might require some adjustment on other PCs. It takes all required info
as parameters.

```bash
bin/setup-tap-vde.sh -u USER -i IP_ADDRESS -g GATEWAY -e PHYSICAL_DEVICE

# For example
bin/setup-tap-vde.sh -u username -i 192.168.0.10/24 -g 192.168.0.1 -e eth0
```

## Usage

The server can be started with:

```bash
aetherscale
```

For example, to list all running VMs run the following client command:

```bash
aetherscale-cli list-vms
```

## Run Tests

You can run tests with `tox`:

```bash
tox
```


## Overview

Components which I think would be interesting to develop are:

- Firewall (probably nftables, so that I can learn nftables)
- Virtual Private Networks (probably tinc)
- Virtual Servers (probably qemu)
  - IPv6-only intranet to learn IPv6

### Creating VMs

When you want to create a new VM, you have to use a *base image*. This is an
already prepared QEMU image in `qcow2` format that will be used to start your
machine.

You can define a custom script that is run on the first start of the machine.
This can be used to install additional software or to configure software.
The init-script is run by systemd and its output can be monitored with

```bash
journalctl -f -u aetherscale-init
```

Execution after the first boot of the machine is prohibited by a conditions
file (cf. in `/etc/systemd/system/aetherscale-init.service`). If you
want to run your script during another boot, you can delete the conditions
file.

## Architecture

My idea is that all requests to the system go through a central message
broker. Handlers will then pick up these tasks and perform the work.

Each request can have the name of a unique channel for responses. The sender
of a message can open a channel with this name on the broker and will receive
responses. This is useful if you have to wait until another component has
performed their work.

### Messages

Create a new machine:

```json
{
   "component": "computing",
   "task": "create-vm",
   "response-channel": "unique-channel-123456789",
   "options": {
      "image": "my-image",
      "virtual-network": "my-virtual-subnet",
      "public-ip": true,
   }
}
```

### Computing

Stuff I use for computing (and thus have learnt something about so far):

- Qemu
- software bridging with `ip` (for public and private IPs)
  - VDE could also be relevant, but currently out of scope
- layer-2 VPN with tinc
- `libguestfs` for analyzing and changing images


## Contribution

If you want to contribute you can:

- create some steampunk artwork for this project :)
- think about what else could be interesting to implement (especially if
  it runs as a daemon it should be based on well-established Linux technology
  that runs without babysitting it all day long)
- create a routine for simple setup of the root installation steps
