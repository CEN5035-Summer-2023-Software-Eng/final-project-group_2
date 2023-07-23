from elasticsearch import Elasticsearch, helpers
import csv
from dotenv import find_dotenv, load_dotenv
import os

# Load environment from .env file
env_elastic = find_dotenv(".env")
load_dotenv(env_elastic)

# Connect to Elastic search cloud
es = Elasticsearch(
    cloud_id=os.environ.get("cloud_id"),
    basic_auth=(os.environ.get("elastic_username"), os.environ.get("elastic_password"))
)

# Index name to be created
index_name = 'nyc-dropofflocations'

# Path to all the CSV files
csv_files_path = './app/data'

# Function to read data from csv and index it in Elasticsearch
def index_data_from_csv():
    docs_count = 0
    # Check if index exists
    #response = es.indices.exists(index=index_name)
    #if response:
    #    return "Index existed!"
    #else:
    # Read all the csv files
    for filename in os.listdir(csv_files_path):
        if filename.endswith(".csv"):
            csv_file = os.path.join(csv_files_path, filename)
            # Read each csv file and check for errors
            with open(csv_file, 'r', encoding='utf-8') as file:
                csv_reader = csv.DictReader(file)
                try:
                    successes, errors = helpers.bulk(es, format_documents(csv_reader), index=index_name)
                    docs_count = successes + docs_count
                    print(f"Successfully uploaded {successes} documents from {csv_file}")
                except helpers.BulkIndexError as e:
                    print(f"Failed to ingest the documents from {csv_file}")
                    for error in e.errors:
                        print(error)
    return f"Total documents: {docs_count}"

# Format the columns that we want to insert 
def format_documents(csv_reader):
    for row in csv_reader:
        # Customize the field mappings in every csv column
        doc = {
            'SiteName': row.get('SiteName', None),  # Use None as the default value for missing fields
            'SiteType': row.get('SiteType', None),
            'Borough': row.get('Borough', None),
            'SiteAddress': row.get('SiteAddr', None),
            'Zipcode': row.get('Zipcode', None),
            'PhoneNumber': row.get('PhoneNumber', None),
            'DayHours': row.get('DaysHours', None),
            'Note': row.get('Notes', None),
            'Latitude': row.get('Latitude', None),
            'Longitude': row.get('Longitude', None),
            #'pin': {'location': { 'lat': float(row.get('Latitude', 0.0)), "lon": float(row.get('Longitude', 0.0))}}
            'Location': {"lat": float(row.get('Latitude', 0.0)), "lon": float(row.get('Longitude', 0.0))}
        }
        yield doc # Generate values one at a time


if __name__ == '__main__':
    print(index_data_from_csv())
