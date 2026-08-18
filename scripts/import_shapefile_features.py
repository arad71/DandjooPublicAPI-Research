"""
Import script for using a shape file to populate the Dandjoo Public Regions collection in the MongoDB database

populates regions with the following format
{
    'name':
    'geojson':
    'source':
}

The region information is presented to the user as: "name (source)", with the geojson location outlined on the map.

Arguments:
    1. path to shapefile or zip containing the shapefile:
        </home/file/db_backup.zip>
    2. keys to access name attributes in the shapefile['features']['properties'] dictionary.
        Can be a single item or a comma seperated list: <name_1,name_2,name_3>
        All fields in the name list are joined as a string
    3. key to access source attribute in the shapefile['features']['properties'] dictionary.
        if no key is provided, the script will expect to find the attribute 'name' in the top level of the shapefile dict
    4. [Optional] host to connect to mongoDB database: default = localhost
    5. [Optional] port to connect to mongoDB database: default = 20717

example
    ./import_shapefile_features.py <shapefile> <name_list> <source> <host-optional> <port-optional>
    ./import_shapefile_features.py backup_.zip name_1,name_2 source localhost 20717

"""
import sys

import pymongo
import shapefile


if __name__ == "__main__":
    if len(sys.argv) == 0:
        print('Usage is <shapefile> <feature attribute(s) with name> <region source> <hostname> <port> ')
        exit(0)

    if len(sys.argv) > 5:
        host = sys.argv[4]
        port = int(sys.argv[5])
    else:
        host = 'localhost'
        port = 27017

    mongo_client = pymongo.MongoClient(host, port)

    # https://stackoverflow.com/a/65962760/16388112
    reader = shapefile.Reader(sys.argv[1])
    geojson = reader.__geo_interface__

    names = sys.argv[2]
    if ',' in names:
        feature_name_keys = names.split(',')
    else:
        feature_name_keys = [sys.argv[2]]

    source = sys.argv[3] if len(sys.argv) > 2 else geojson['name']

    collection = mongo_client.public.regions
    for feature in geojson['features']:
        collection.insert_one({
            'name': ' '.join(map(lambda x: feature['properties'][x].strip(), feature_name_keys)),
            "geojson": feature,
            'source': source
        })
    mongo_client.public.regions.create_index([('geojson.geometry', pymongo.GEOSPHERE)])
    exit(0)
