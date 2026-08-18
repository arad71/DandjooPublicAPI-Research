import json
import sys
import pymongo

if __name__ == "__main__":
    if len(sys.argv) == 0:
        print('Usage is <geojsonFile> <key in sub-feature-with name> <region source>')
        exit(0)

    if len(sys.argv) > 5:
        host = sys.argv[4]
        port = int(sys.artv[5])
    else:
        host = 'localhost'
        port = 27017

    mongo_client = pymongo.MongoClient(host, port)

    geojson = json.load(open(sys.argv[1], "r"))
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
