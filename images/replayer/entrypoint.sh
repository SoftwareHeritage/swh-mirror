#!/bin/bash

set -e
if [[ `id -u` == "0" ]] ; then
	# init script run as root

	# ensure volumes mounted in /srv/softwareheritage belong to swh
	chown swh:swh /srv/softwareheritage/*

	# now run this script as swh
	HOME=/srv/softwareheritage exec setpriv --reuid=swh --regid=swh --init-groups $0 $@
fi

# For debugging purpose
if [ -f /etc/softwareheritage/config.yml ]; then
	echo "### CONFIG FILE ###"
	cat /etc/softwareheritage/config.yml || true
fi

echo "###################"
case "$1" in
    "shell"|"sh"|"bash")
		shift
		if (( $# == 0)); then
			exec bash -i
		else
			"$@"
		fi
		;;

    "graph-replayer")
        wait-for-it storage:5002
        echo "Starting the SWH mirror graph replayer"
        exec python3 -m swh --log-level ${LOG_LEVEL:-WARNING} storage replay
        ;;

    "content-replayer")
        wait-for-it objstorage:5003
        echo "Starting the SWH mirror content replayer"
        exec python3 -m swh --log-level ${LOG_LEVEL:-WARNING} objstorage replay
        ;;
esac
