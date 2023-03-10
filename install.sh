#!/bin/bash

# set permissions for script files
chmod a+x /data/dbus-solax-x1-pvinverter/restart.sh
chmod 744 /data/dbus-solax-x1-pvinverter/restart.sh

chmod a+x /data/dbus-solax-x1-pvinverter/uninstall.sh
chmod 744 /data/dbus-solax-x1-pvinverter/uninstall.sh

chmod a+x /data/dbus-solax-x1-pvinverter/service/run
chmod 755 /data/dbus-solax-x1-pvinverter/service/run



# create sym-link to run script in deamon
ln -s /data/dbus-solax-x1-pvinverter/service /service/dbus-solax-x1-pvinverter



# add install-script to rc.local to be ready for firmware update
filename=/data/rc.local
if [ ! -f $filename ]
then
    touch $filename
    chmod 755 $filename
    echo "#!/bin/bash" >> $filename
    echo >> $filename
fi

grep -qxF '/data/dbus-solax-x1-pvinverter/install.sh' $filename || echo '/data/dbus-solax-x1-pvinverter/install.sh' >> $filename
