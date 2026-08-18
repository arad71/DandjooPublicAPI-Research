#!/usr/bin/env python3
"""
This script can be used to report, clear, and restore threat_status values to the database.

Database connection arguments were copied from similar scripts.
A new value -act or --action was added to control what the script does. argument options:
1. report: [default value if not specified] Create a csv listing all records with threat statuses - no change to DB
2. clear: Clear the threat statuses of all records in the DB. Creates a new csv report if none exists.
3. restore: Opens the most recent csv report generated from option 1 or 2, and sets the threat statuses in the DB.

This script was written specifically to aid in testing obfuscation and species list implementation.
The intention was to use this script in the dandjoo public staging server to remove all threat statuses,
then curate a special set of threatened species. This process will allow the tester to know how many threatened species
should be present while viewing records through the web portal. Once testing in the staging server is complete,
the modified threat statuses can be returned using the 'restore' option of the script.

Intended use: run this script from a terminal in the app/scripts directory. The report csv is created in the location
of the terminal when using the 'report' or 'clear' options. The 'restore' option expects the csv report to be in the
location of the terminal.
"""

import argparse
import glob
import os
import sys
import time
import csv


from pymongo import MongoClient, UpdateOne


def parse_args():
    """
    Parse command-line arguments.

    Returns:
        argparse.Namespace: Parsed arguments.
    """
    parser = argparse.ArgumentParser(description='Populate public collection with data from taxonomy collection')

    # public database access details
    parser.add_argument('-ph', '--public_host', dest='public_host', action='store',
                        default='localhost', help='Specify the public mongo host uri')

    parser.add_argument('-pp', '--public_port', dest='public_port', action='store',
                        default=27017, help='Specify the public mongo host port')

    parser.add_argument('-pu', '--public_user', dest='public_username', action='store',
                        default='', help='Specify the mongo username')

    parser.add_argument('-ppw', '--public_password', dest='public_password', action='store',
                        default='', help='Specify the mongo password')

    # databases
    parser.add_argument('-pdb', '--public_database', dest='public_database', action='store',
                        default='public', help='Specify the public database name')

    # collections
    parser.add_argument('-rc', '--records_collection', dest='records_collection', action='store',
                        default='records', help='Specify the mongo public records collection')

    # script actions
    parser.add_argument('-act', '--action', action='store',
                        choices=['report', 'clear', 'restore'], default='report',
                        help='Specify the action for the script: report, clear, or restore')
    return parser.parse_args()


class ThreatStatusChanger:
    """
    Class to handle operations related to threat statuses in the database.
    """
    @staticmethod
    def make_list_of_threat_statuses(records_collection):
        """
        Creates a list of records with threat statuses and saves it to a CSV file.

        Args:
            records_collection (pymongo.collection.Collection): MongoDB collection object.

        Returns:
            list: List of dictionaries containing 'persistent_id', 'scientific_name', and 'threat_status'.
        """
        threat_statuses = []
        cursor = records_collection.find({'threat_status': {'$exists': True, '$ne': '', '$ne': None}},
                                         {'persistent_id': 1, 'scientific_name': 1, 'threat_status': 1})

        for record in cursor:
            threat_status_entry = {
                'persistent_id': record['persistent_id'],
                'scientific_name': record['scientific_name'],
                'threat_status': record['threat_status']
            }
            threat_statuses.append(threat_status_entry)

        # Save the data to a CSV file
        file_name = f'threat_status_summary_{time.strftime("%d%m%Y-%H%M%S")}.csv'
        with open(file_name, 'w+', newline='') as csv_file:
            csv_writer = csv.DictWriter(csv_file, fieldnames=['persistent_id', 'scientific_name', 'threat_status'])
            csv_writer.writeheader()
            csv_writer.writerows(threat_statuses)

        return threat_statuses

    @staticmethod
    def get_statuses_from_csv():
        """
        Retrieves threat statuses from the most recent CSV file.

        Returns:
            list: List of dictionaries containing 'persistent_id', 'scientific_name', and 'threat_status'.
                  Returns None if no CSV file is found.
        """
        # Get the list of CSV files in the current directory
        csv_files = glob.glob('threat_status_summary_*.csv')

        # Check if any CSV files exist
        if not csv_files:
            return None

        # Get the most recent CSV file based on modification time
        latest_csv_file = max(csv_files, key=os.path.getmtime)

        # Read data from the most recent CSV file
        threat_statuses = []
        with open(latest_csv_file, 'r', newline='') as csv_file:
            csv_reader = csv.DictReader(csv_file)
            for row in csv_reader:
                threat_statuses.append(row)

        # Return the threat_statuses data read from the CSV file
        return threat_statuses

    @staticmethod
    def set_database_threat_status_values(records_collection, threat_status_list):
        """
        Sets threat statuses in the database based on the provided list of records.

        Args:
            records_collection (pymongo.collection.Collection): MongoDB collection object.
            threat_status_list (list): List of dictionaries containing 'persistent_id', 'scientific_name',
                                       and 'threat_status'.
        """
        bulk_updates = []

        for entry in threat_status_list:
            record_id = entry['persistent_id']
            new_threat_status = entry['threat_status']

            # Create an update operation for each document
            update_operation = UpdateOne(
                {'persistent_id': record_id},
                {'$set': {'threat_status': new_threat_status}}
            )
            bulk_updates.append(update_operation)

        # Execute bulk updates
        if bulk_updates:
            try:
                records_collection.bulk_write(bulk_updates)
                print(f"Restore action complete: [{len(bulk_updates)}] update operations executed successfully.")
            except Exception as e:
                print(f"Error executing bulk updates: {e}")

    @staticmethod
    def clear_database_threat_statuses(records_collection):
        """
        Clears the threat statuses of all records in the database.

        Args:
            records_collection (pymongo.collection.Collection): MongoDB collection object.
        """
        try:
            # Clear the threat_status field for all records where the value exists
            result = records_collection.update_many(
                {'threat_status': {'$exists': True, '$ne': '', '$ne': None}},
                {'$set': {'threat_status': None}}
            )
            print(f"Clear action complete: [{result.modified_count}] threat statuses cleared successfully.")
        except Exception as e:
            print(f"Error clearing threat statuses: {e}")


if __name__ == '__main__':
    args = parse_args()

    # get records collection
    public_client = MongoClient(args.public_host, args.public_port, username=args.public_username,
                                password=args.public_password)
    public_records_collection = public_client[args.public_database][args.records_collection]

    # Handle different script actions based on args.script_action value
    # Option 1: REPORT
    # This option prints the number of records that have a threat status, and creates a csv with the threat status,
    # persistent id, and scientific name of each record.
    if args.action == 'report':
        threat_list = ThreatStatusChanger.make_list_of_threat_statuses(public_records_collection)
        print(f'Report action complete: [{len(threat_list)}] records identified. '
              f'Inspect threat status summary csv for more information.')
    # Option #2: CLEAR
    # This option removes the threat statuses of all records in the database.
    # It also creates a list csv report of the records with threat statuses before performing the clear operation to
    # make sure the restore action can be performed in case the caller doesn't have a viable copy of the report already.
    elif args.action == 'clear':
        current_list = ThreatStatusChanger.get_statuses_from_csv()
        if not current_list or not len(current_list):
            print(f"Clear action started - no csv report found at terminal location - creating report csv.")
            ThreatStatusChanger.make_list_of_threat_statuses(public_records_collection)
            # validate the report before processing the clear action
            current_list = ThreatStatusChanger.get_statuses_from_csv()
            if not current_list or not len(current_list):
                print(f'Clear action aborted: Problem encountered while attempting to create csv report.')
                sys.exit(1)
        ThreatStatusChanger.clear_database_threat_statuses(public_records_collection)

    # Option #3: RESTORE
    # This option opens the most recent csv report, and sets the threat statuses in the database to match those of the
    # persistent ids in the report
    elif args.action == 'restore':
        restore_list = ThreatStatusChanger.get_statuses_from_csv()
        if restore_list and len(restore_list):
            ThreatStatusChanger.set_database_threat_status_values(public_records_collection, restore_list)
        else:
            print("Error: Could not load threat statuses from csv file.")

    else:
        print('Invalid script action. Please specify report, clear, or restore.')
