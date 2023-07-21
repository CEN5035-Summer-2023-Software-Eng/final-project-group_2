import os
import uuid
import base64
import json
from datetime import datetime
from flask import Flask, request, render_template, jsonify, send_file
from model.model import tf_predict, read_imagefile
from io import BytesIO
from elasticsearch import Elasticsearch
from elasticsearch.exceptions import NotFoundError
from dotenv import find_dotenv, load_dotenv



app = Flask(__name__)


# Load environment from .env file
env_elastic = find_dotenv(".env")
load_dotenv(env_elastic)

# Connect to Elastic search cloud
es = Elasticsearch(
    cloud_id=os.environ.get("cloud_id"),
    basic_auth=(os.environ.get("elastic_username"), os.environ.get("elastic_password"))
)

# Directory to store the images locally (we can remove this later since we will store the image in elastic search)
IMAGES_DIR = "./wasteimages/"
if not os.path.exists(IMAGES_DIR):
    os.makedirs(IMAGES_DIR)



@app.route("/")
def index():
    return render_template("index.html")


# POST request to predict image by uploading the image file
@app.route("/predict/image", methods=["POST"])
def predict_api():
    file = request.files["file"]
    username = request.form.get("username")
    # Check if images are in the correct format
    extension = file.filename.split(".")[-1] in ("jpg", "jpeg", "png")
    if not extension:
        return jsonify({"message": "Image must be in jpg, jpeg, or png format!"}), 400
    
    # Validate username 
    if not username:
        return jsonify({"message": "Cannot find authenticated user!"}), 400

    try:
        # Read the file and return it as PIL image and then predict it
        image_data = file.read()
        image = read_imagefile(image_data)
        waste_type, confidence_score = tf_predict(image) # tf_predict and read_imagefile functions locate in model.py

        # Generate a unique ID 
        image_id = str(uuid.uuid4())
        # Save the image to the images directory with the generated image_id as the filename
        image_path = os.path.join(IMAGES_DIR, f"{image_id}.jpg")
        
        # Save the image locally - We will not save this locally
        #image.save(image_path)

        # Convert the PIL image to bytes
        image_bytes = BytesIO()
        image.save(image_bytes, format="JPEG")
        image_bytes = image_bytes.getvalue()

        # Convert the bytes to base64 encoding
        base64_image = base64.b64encode(image_bytes).decode("utf-8")
        
        # Information that we will be storing in the elastic cloud
        doc = {
            "image_id": image_id,
            "username": username,
            "waste_type": waste_type,
            "confidence_score": confidence_score,
            "image_filename": file.filename,
            "image_path": image_path,
            "image_binary": base64_image,
            "date": datetime.now()
        }
        # Ingest the data
        es.index(index="wasteclassified", document=doc)
        # Send results as json format (only including id, waste type, and confidence score)
        return jsonify({"image_id": image_id, "waste_type": waste_type, "confidence_score": confidence_score}), 200

    except Exception as e:
        return jsonify({"message": str(e)}), 500

# Display the image using image_id
@app.route("/display/<image_id>")
def display_image(image_id):
    try:
        # Retrieve the image from Elasticsearch based on image_id
        res = es.search(
            index="wasteclassified",
            query={
                "match": {"image_id": image_id}
            }
        )
        # Check if found any result
        hits = res['hits']['hits']
        if not hits:
            raise NotFoundError("Image not found in the index.")

        # If so, get binary value from image 
        source = hits[0]['_source']
        image_binary = source["image_binary"]

        # Create a BytesIO object from the base64 image data
        img_bytes = base64.b64decode(image_binary)

        # Send the image file to the browser
        return send_file(BytesIO(img_bytes), mimetype="image/jpeg")

    except NotFoundError as e:
        # Raise error when the image_id is not found
        return jsonify({"error": "Image not found."}), 404
    except Exception as e:
        # Other error
        return jsonify({"error": str(e)}), 500


# Function to read JSON file and get waste type information
def get_waste_info(waste_type):
    with open('./wasteinfo.json', 'r') as file:
        data = json.load(file)
    for item in data['waste_types']:
        if item['name'].lower() == waste_type.lower():
            return item['category'], item['description']
    return None, None


# GET waste type information given waste type
@app.route("/waste/<waste_type>", methods=["GET"])
def get_waste_type_info(waste_type):
    category, description = get_waste_info(waste_type)
    if category and description:
        return jsonify({
            "waste_type": waste_type,
            "category": category,
            "description": description
        })
    else:
        return jsonify({"error": f"{waste_type} was not found in the waste types data."}), 404

# POST request that returns drop-off locations based on SiteType and Zipcode
@app.route("/searchByZipCodeSiteType", methods=["POST"])
def search_location():
    # Get the data from the form data in the POST request
    Zipcode = request.form.get("Zipcode")
    SiteType = request.form.get("SiteType")


    # Check if inputs are empty
    if not Zipcode or not SiteType:
        return jsonify({"error": "Please fill out both Zipcode and SiteType fields."}), 400

    try:
        ##### This search query will only find locations based on exact Zipcode and SiteType #####
        #res = es.search(
        #    index='nyc-dropofflocations',
        #    query={
        #        "bool": {
        #                "must": [
        #                    {"match": {"Zipcode": Zipcode}},
        #                    {"match": {"SiteType": SiteType}}
        #                ]
        #            }
        #    }
        #)

        #### This search query will find locations by filtering the SiteType first 
        #### and then looking for matching values in both Zipcode and SiteAddress.
        #### The reason I prefer this way because some csv files do not contain Zipcode column,
        #### so we might want to find the matching values in the SiteAddress
        res = es.search(
                index='nyc-dropofflocations',
                query={
                    "bool": {
                        "filter": [
                            {"term": {"SiteType": SiteType}}
                        ],
                        "must": [
                            {"multi_match": {
                                "query": Zipcode,
                                "fields": ["Zipcode", "SiteAddress"],
                                "type": "best_fields"
                            }}
                        ]
                    }
                }
        )

        # Check if result has been found
        hits = res['hits']['hits']
        if not hits:
            return jsonify({"error": "Data not found for the provided Zipcode and SiteType."}), 404

        # Store the results 
        source_list = [hit["_source"] for hit in hits]
        return jsonify(source_list), 200

    except NotFoundError as e:
        # Raise error when data is not found
        return jsonify({"error": "Data not found for the provided Zipcode and SiteType."}), 404
    except Exception as e:
        # Other errors 
        return jsonify({"error": str(e)}), 500


# GET request to get unique values in the "SiteType" field for dropdown 
@app.route("/findAllSiteTypes", methods=["GET"])
def get_unique_sitetypes():
    try:
        # Get all unique values in the "SiteType" field
        res = es.search(
            index='nyc-dropofflocations',
            query={
                    "match_all": {}},
            aggs={
                    "unique_values": {
                        "terms": {
                            "field": "SiteType"
                        }
                    }
                }
        )
        # Store the results
        #print(res["aggregations"]["unique_values"]["buckets"])
        unique_sitetypes = [bucket["key"] for bucket in res["aggregations"]["unique_values"]["buckets"]]
        return jsonify(unique_sitetypes)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# GET request to retrieve all the field names of 'wasteclassified' index for dropdown (History Tab)
@app.route("/findAllWasteFields/<index>", methods=["GET"])
def get_field_names(index):
    try:
        # Get the mapping 
        mapping = es.indices.get_mapping(index=index)

        # Store results excluding "image_binary", "username", and "image_path" fields
        excluded_fields = ["image_binary", "username", "image_path"]
        field_names = [field for field in mapping[index]["mappings"]["properties"].keys() if field not in excluded_fields]

        return jsonify(field_names), 200
    
    except NotFoundError as e:
        # Raise error when data is not found
        return jsonify({"error": "Results not found."}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500



# POST request that returns the classified waste info based on username (owner), field name, and query (History Tab)
@app.route("/findInfoByUsernameAndField", methods=["POST"])
def search_info():
    # Get the data from the form data in the POST request
    username = request.form.get("username")
    field = request.form.get("field")
    query = request.form.get("query")


    # Check if inputs are empty
    if not field or not query:
        return jsonify({"error": "Please fill out both the field and query."}), 400
    elif not username:
        return jsonify({"error": "Cannot find authenticated user!"}), 400

    try:
        res = es.search(
            index="wasteclassified",
            source_excludes=["image_binary","image_path","username"],   # Exclude image_binary for the final result (we can add this if we want to add images)
            size=15,                          # Limit 15 results
            query={
                    "bool": {
                        "filter": [
                            {"term": {"username": username}}   # Filter by username and field   
                        ],
                        "should": [
                            {
                                "regexp": {
                                    f"{field}": {
                                        "value": f".*{query}.*",
                                        "flags": "ALL",
                                        "case_insensitive": True
                                    }
                                }
                            }
                        ]
                    }
                }
        )

        # Check if result has been found
        hits = res['hits']['hits']
        if not hits:
            return jsonify({"error": "Data not found!"}), 404

        # Store the results 
        source_list = [hit["_source"] for hit in hits]
        return jsonify(source_list), 200

    except NotFoundError as e:
        # Raise error when data is not found
        return jsonify({"error": "Data not found."}), 404
    except Exception as e:
        # Other errors 
        return jsonify({"error": str(e)}), 500
    
# Function that counts the unique values within a field name
def count_unique_values_by_field(data_list,field_name):
    counts_dict = {}
    for item in data_list:
        value = item.get(field_name)
        if value:
            counts_dict[value] = counts_dict.get(field_name,0) + 1
    return counts_dict

# GET request to get number of unique values within a field name based on username (Portfolio Tab)
@app.route("/findNumUniqueValuesWithinFieldByUsername", methods=["GET"])
def get_num_unique():
    # Get the inputs
    username = request.args.get("username")
    field_name = request.args.get("field_name")

    # Validate inputs
    if not username or not field_name:
        return jsonify({"error": "Please specify both username and field_name!"}), 404
    # Validate field_name:
    accepted_field_name = ["image_id","waste_type","confidence_score","image_filename"]
    if field_name not in accepted_field_name:
        return jsonify({"error": "The field_name you entered was not valid!"}), 404
    
    try:
        # Get all unique values in a chosen field
        res = es.search(
            index='wasteclassified',
            source_excludes=["image_binary","image_path","username"],   # Exclude some fields
            query={
                    "bool": {
                        "must": [
                            {"match": {"username": username}}
                        ]}
            }
        )

        # Check if result has been found
        hits = res['hits']['hits']
        if not hits:
            return jsonify({"error": "Data not found!"}), 404

        # Store the results 
        source_list = [hit["_source"] for hit in hits]
        
        # Extract the chosen field and count unique values
        count_dict = count_unique_values_by_field(source_list,str(field_name))

        # Format the result as a dictionary
        return jsonify(count_dict)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
