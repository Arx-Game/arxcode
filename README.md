[![Build Status](https://travis-ci.org/Arx-Game/arxcode.svg?branch=stable_orphan)](https://travis-ci.org/Arx-Game/arxcode)

Arx is a game based on Evennia. I decided to make an orphan branch open source to let people
use code as they like for their own games and contribute if they like. In general we should
be compatible with any given Evennia branch, though I tend to stay on master and occasionally
make a branch to cherry-pick additions from develop.

The basic requirements  are added in the different setup files. Evennia sets the django settings
environmental variable at startup and looks specifically in the server/conf/ directory, so specify
`--settings=foo_settings` where `foo_settings` is a settings file in the server/conf/ directory.
The default will use production_settings unless otherwise specified.

Some django packages aren't compatible with Evennia due to clashes in middleware. Silk,
for example, will throw errors from its middleware whenever an in-game script runs.

Evennia resources:

From here on you might want to look at one of the [beginner tutorials](https://github.com/evennia/evennia/wiki/Tutorials).

Evennia's documentation is [here](https://github.com/evennia/evennia/wiki).

Griatch wrote a great guide to installing arx [here](https://github.com/evennia/evennia/wiki/Arxcode-installing-help).
Enjoy!

----

## Docker

This will cover getting Arx up and running using a Docker container and docker compose. The purpose of this is to provide ease of use in development and is not meant to be used in a production environment.

### Setup

1. Install Docker
2. Install Docker Compose
3. Run the init script (./init.sh)
  * If you want to use the sample-development.env file, run the init script with the setup-env argument (./init.sh setup-env) 
  * Once completed, kill the running docker process.

The init script will build the evennia db, build the docker file, and set the state.

A very basic environment file is attached in sample-development.env, which will give you a running local instance that can be connected to from localhost.

The server is localhost:3000
The portal is localhost:8000

If you wish to use those settings, you can run the default-env.sh script

### Running Instance

In general, once the init script is run, all you have to do to start the server is docker-compose up. Changes made to the code base will not be represented in the default version.

#### Running Instance With Live Changes

In order to run the service in a live mode to support changes, you need to run the following command.

```
docker-compose -f docker-compose-live.yaml up
```

This mounts the entire bin directory to the most recent version of the arx:latest image.

In order to reload live changes, you need to do the following:

```
docker container ls
```

The result should look something like this:

```
CONTAINER ID        IMAGE               COMMAND             CREATED             STATUS              PORTS                    NAMES
1e5d4de22d3b        arx:latest          "start"             2 minutes ago       Up 2 minutes        0.0.0.0:3000->3000/tcp   arxcode_arx_1
```

After this, run the following command:

```
docker exec 1e5d4de22d3b evennia reload
```

This will restart the server with the live modifications from your local directory.
