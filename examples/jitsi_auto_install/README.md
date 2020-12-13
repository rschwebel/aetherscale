Jitsi auto install
==================

Jitsi requires some host-specific configuration during installation and
according to their forum it is easier to re-install the package with right
configuration than to edit an existing installation.
At least this goes for the automatic installation using the debian package.
With the manual installation, we'd have all freedom. But let's stick to the
deb-installation.

This means, we will use a per-host script that is executed on the host
during startup.

For this, we will create a systemd unit that is execute in case a specific
folder (`/etc/jitsi`) does not exist. This unit will then perform an
unattended install of Jitsi.

To achieve this, the systemd unit has to be installed into the QEMU image
before boot. We achieve this with `guestmount`. All steps to change the image
are given in `modify-image.sh`.

As of the time of writing this guide, there is no functionality inside
`aetherscale` to define ones own user script to execute during host boot.
Since the environment variable `JITSI_HOSTNAME` has to be set differently
for each VM it also does not work to prepare an image with these steps. Thus,
at the time of writing this can only serve as an example what could be possible
with a few modifications.
