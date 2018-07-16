#!/bin/sh

sudo service apache24 stop
make drop-db create-db
sudo -u bazaar make init-db
make load-seatgeek load-fixtures
sudo service apache24 start
