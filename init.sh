#!/usr/bin/env bash

case "$1" in
  setup-env) cp sample-development.env config.env
             ln -s config.env .env
            ;;
          esac

# build the container
docker build -t arx .


# create database
docker run -itv "$(pwd)"/server:/usr/src/arx/server arx:latest evennia migrate

# create the logs directory
mkdir -p ./server/logs

# initialize the database
docker run -itv "$(pwd)"/server:/usr/src/arx/server arx:latest start
