#!/usr/bin/env python3

import sys
import argparse
import pymongo
import requests

BIOSYS_API_PATH = 'api'
BIOSYS_AUTH_PATH = 'auth-token'
BIOSYS_PROJECTS_PATH = 'projects'
BIOSYS_DATASETS_PATH = 'datasets'
BIOSYS_RECORDS_PATH = 'records'
BIOSYS_RECORD_BUFFER_SIZE = 1000


def urljoin(*args):
    return f'{"/".join(map(lambda x: str(x).rstrip("/"), args))}/'


def parse_args():
    parser = argparse.ArgumentParser(description='Populate MongoDB collection with records from Biosys species '
                                                 'datasets')

    parser.add_argument('-bh', '--biosys_host', dest='biosys_host', action='store', default='localhost',
                        help='specify the biosys host uri')

    parser.add_argument('-bp', '--biosys_port', dest='biosys_port', action='store', default=80,
                        help='specify the biosys host port')

    parser.add_argument('-bu', '--biosys_user', dest='biosys_username', action='store', default='admin',
                        help='specify the biosys username')

    parser.add_argument('-bpw', '--biosys_password', dest='biosys_password', action='store', default='password',
                        help='specify the biosys password')

    parser.add_argument('-mh', '--mongo_host', dest='mongo_host', action='store', default='localhost',
                        help='specify the mongo host uri')

    parser.add_argument('-mp', '--mongo_port', dest='mongo_port', action='store', default=27017,
                        help='specify the mongo host port')

    parser.add_argument('-mu', '--mongo_user', dest='mongo_username', action='store', default='',
                        help='specify the mongo username')

    parser.add_argument('-mpw', '--mongo_password', dest='mongo_password', action='store', default='',
                        help='specify the mongo password')

    parser.add_argument('-mdb', '--mongo_database', dest='mongo_database', action='store', default='public',
                        help='specify the mongo database')

    parser.add_argument('-mc', '--mongo_collection', dest='mongo_collection', action='store', default='records',
                        help='specify the mongo collection to load records too')

    parser.add_argument('dataset_names', nargs=argparse.REMAINDER, help='dataset names of Biosys species records')

    return parser.parse_args()


def setup_auth_token(biosys_url, username, password):
    auth_url = urljoin(biosys_url, BIOSYS_API_PATH, BIOSYS_AUTH_PATH)

    response = requests.post(auth_url, data={'username': username, 'password': password})

    if response.status_code == requests.codes.OK:
        token = response.json()['token']

        request_session = requests.Session()
        request_session.headers.update({'Authorization': f'Token {token}'})

        return request_session
    else:
        print(f'Error authenticating: {response.text}')
        sys.exit(response.status_code)


def get_datasets(session, biosys_url, dataset_names):
    datasets_url = urljoin(biosys_url, BIOSYS_API_PATH, BIOSYS_DATASETS_PATH)

    datasets = []
    for dataset_name in dataset_names:
        response = session.get(datasets_url, params={'name': dataset_name})

        if response.status_code == requests.codes.OK and len(response.json()) > 0:
            datasets = datasets + response.json()
        else:
            print(f'Error finding dataset {dataset_name}')

    return datasets


def get_project(project_id):
    project_url = urljoin(biosys_url, BIOSYS_API_PATH, BIOSYS_PROJECTS_PATH, project_id)
    response = session.get(project_url)

    if response.status_code == requests.codes.OK:
        return response.json()
    else:
        print(f'Error getting project for project with id {project_id}: {response.text}')
        return []


def get_records_for_dataset(session, biosys_url, dataset, limit=None, offset=0):
    dataset_records_url = urljoin(biosys_url, BIOSYS_API_PATH, BIOSYS_DATASETS_PATH, dataset['id'], BIOSYS_RECORDS_PATH)

    project = get_project(dataset['project'])

    params = {
        'offset': offset
    }
    if limit is not None:
        params['limit'] = limit

    response = session.get(dataset_records_url, params=params)

    if response.status_code == requests.codes.OK:
        records = response.json()['results']
        for record in records:
            record['dataset'] = dataset['name']
            record['project'] = project['name']

        return records
    else:
        print(f'Error getting records for dataset {dataset["name"]}: {response.text}')
        return []


def tranform_biosys_to_mongo(biosys_records):
    return map(lambda biosys_record: {
        'location': biosys_record['geometry'],
        'date': biosys_record['datetime'],
        'species': biosys_record['species_name'],
        'dataset': biosys_record['dataset'],
        'data_provider': biosys_record['project']
    }, biosys_records)


def push_dataset_to_collection(session, biosys_url, dataset, collection):
    record_count = dataset['record_count']
    offset = 0

    print(f'Transferring records from {dataset["name"]}')
    while offset < record_count:
        record_num_min = offset
        record_num_max = record_num_min + BIOSYS_RECORD_BUFFER_SIZE if record_num_min + BIOSYS_RECORD_BUFFER_SIZE < \
            record_count else record_num_min + record_count % BIOSYS_RECORD_BUFFER_SIZE
        print(f'{offset} - {record_num_max} of {record_count}')

        biosys_records = get_records_for_dataset(session, biosys_url, dataset, BIOSYS_RECORD_BUFFER_SIZE, offset)

        if len(biosys_records) > 0:
            mongo_records = tranform_biosys_to_mongo(biosys_records)
            collection.insert_many(mongo_records)

        offset = offset + BIOSYS_RECORD_BUFFER_SIZE


if __name__ == '__main__':
    args = parse_args()

    biosys_url = f'{args.biosys_host.rstrip("/")}:{args.biosys_port}'

    session = setup_auth_token(biosys_url, args.biosys_username, args.biosys_password)

    datasets = get_datasets(session, biosys_url, args.dataset_names)

    client = pymongo.MongoClient(args.mongo_host, args.mongo_port, username=args.mongo_username,
                                 password=args.mongo_password)

    collection = client[args.mongo_database][args.mongo_collection]

    for dataset in datasets:
        push_dataset_to_collection(session, biosys_url, dataset, collection)
