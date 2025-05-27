#!/bin/bash
# /cassandra-override.yml is provided by docker swarm via a 'config' object, and only
# contains entries that cannot be set using environment variables. Add them at
# the end of the existing config file provided by the docker image so they take
# precedence (last talker wins).
cat /cassandra-override.yml >> /etc/cassandra/cassandra.yaml

# stolen from https://github.com/guard-systems/cassandra_swarm
# Wait 15 seconds to be sure that all nodes in the swarm has started and are available in DNS
sleep 15s
ownip="$(hostname)"
# dont have nslookup, so use python instead...
#export CASSANDRA_SEEDS="$(nslookup tasks.$SERVICENAME | grep 'Address'| grep -v '127.0.0.1' | cut -d: -f2 | awk '{ print $1}' | sort | xargs | sed 's/ /,/g')"
export CASSANDRA_SEEDS="$( python3 -c "import sys;import socket;print(','.join(sorted(socket.gethostbyname_ex(sys.argv[1])[2])))" tasks.$SERVICENAME )"
export CASSANDRA_BROADCAST_ADDRESS=$ownip;
echo $CASSANDRA_SEEDS
echo $CASSANDRA_BROADCAST_ADDRESS


exec docker-entrypoint.sh
