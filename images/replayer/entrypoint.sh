#!/bin/bash

set -e

# generate the config file from the 'template'
if [ -f /etc/softwareheritage/config.yml.tmpl ]; then
	# I know... I know!
	eval "echo \"`cat /etc/softwareheritage/config.yml.tmpl`\"" > \
		 /etc/softwareheritage/config.yml
fi

# For debugging purpose
echo "### CONFIG FILE ###"
cat /etc/softwareheritage/config.yml
echo "###################"


case "$1" in
    "shell"|"sh"|"bash")
        exec bash -i
        ;;
    "graph-replayer")
		wait-for-it storage:5002
        echo "Starting the SWH mirror graph replayer"
        exec sh -c "trap : TERM INT; while :; do swh --log-level ${LOG_LEVEL:-WARNING} storage replay; done"
        ;;
    "content-replayer")
		wait-for-it objstorage:5003
        echo "Starting the SWH mirror content replayer"
        exec sh -c "trap : TERM INT; while :; do swh --log-level ${LOG_LEVEL:-WARNING} objstorage replay; done"
        ;;
esac
