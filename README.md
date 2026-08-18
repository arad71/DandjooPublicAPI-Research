# WA BDR / Dandjoo Public API

# Getting started

## Context

This repository contains code for setting up and running public API for the Dandjoo, foremerly WA-BDR, project.

## Development server

### Dependent systems.

MongoDB and Geoserver with the MongoDB plugin are required to run the system for development. These are configured to
run in docker containers, which are configured via Docker Compose. This can be run via the following command:

```bash
docker-compose up -d
```

This will automatically include the docker-compose.override.yml configuration, which exposes necessary ports.

When using the mongodb atlas container locally you need to connect with `directConnection=true` due to the atlas
being a replicaset 

### Running FastAPI app locally

The FastAPI app _can_ be run in Docker, although it's easier to debug if run locally. First, however, it's strongly
advised to use a Python Virtual Environment for hosting Python dependent libraries. See https://docs.python.org/3/tutorial/venv.html
for details on how to do this.

Once your virtual environment is set up and activated, install the dependent libraries. These are maintained by
[Python Poetry](https://python-poetry.org/), which must be installed before dependencies can be installed. See the
installation instructions [here](https://python-poetry.org/docs/#installation). Once installed, the dependencies can
be installed by:

```bash
poetry install
```

**When using with local mongo atlas container need to use the `MONGODB_DIRECT_CONNECTION=True`** environment variable

Finally, to run the fastapi app:
`uvicorn app.main:app --reload`

On a Mac run command from inside poetry
`poetry run uvicorn app.main:app --reload`

Note - most likely in development there will be no access to deployed auth infrastructure, in which case you should run:
`DEV_AUTH=True uvicorn app.main:app --reload`

On a Mac run command from inside poetry
`DEV_AUTH=True poetry run uvicorn app.main:app --reload`

This will bypass authentication checks and use a default test user with all permissions.

## Setting up database

The mongo database will generally set itself up as its collections are populated. However, the various indexes need to
be specified manually. To do this, run the following script (either before or after loading data):

When using the mongodb atlas container locally you need to connect with `directConnection=true` due to the atlas
being a replicaset 

```
scripts/setup_mongo_collections.py [-mh mongo_host] [-mp mongo_port] [-mu mongo_username] [-mpw mongo_password] [-mdb mongo_database]
```

## Loading data

To import BIOSYS data into the local instance:

```
scripts/biosys_species_obs_to_mongo_col.py -bh <URL> -bu <username> -bpw <password> <DATASETNAME>
```

### Running load scripts in a Docker-compose stack

In a staging or production environment where container ports are not exposed, the load scripts (including the above)
need to run in the same Docker-compose stack to be able to connect to other containers (namely the database) via the
stack's private network.

To allow this, a `cli` container is defined in docker-compose.yml which has Python dependencies loaded and will run
within the private network. To run a command within this container:

```shell
docker-compose run [--rm] cli scripts/<script> [args...]
```

Note the `--rm` will remove the container after is has run, which may be desired.

## Running tests

All tests area located in the /tests directory and are written in PyTest. To run:

`pytest`

## Authentication for pushing / deleting records

In order to allow other systems (i.e. Dandjoo Curation) to push/delete records to/from the Dandjoo Public system, an
authentication key must be set:

`API_SYSTEM_KEY=somekey`

Other systems should set the following request header when sending requests to the Dandjoo Public API record post/delete
endpoints.

`x-api-key: somekey`

## Redis caching

A redis container is defined in docker-compose.override.yml for local development.
Caching is disabled by default by setting the redis host, port, and password environment variables to none.
Local development values: REDIS_HOST=localhost REDIS_PORT=6379 REDIS_PASSWORD=dev_password
