Jitsi auto install
==================

Jitsi requires some host-specific configuration during installation and
according to their forum it is easier to re-install the package with right
configuration than to edit an existing installation.
At least this goes for the automatic installation using the debian package.
With the manual installation, we'd have all freedom. But let's stick to the
deb-installation.

This means, we will use a per-host script that is executed on the host
during startup. An init script can be passed to the VM using `init-script`
in the JSON message or `--init-script` on the command line. The example
Python file reads a jinja2 template and sets a user defined hostname before
starting the VM.
