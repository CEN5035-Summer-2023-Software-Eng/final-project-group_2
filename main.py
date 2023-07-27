from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
import pyrebase
from model.model import tf_predict, read_imagefile
from io import BytesIO
from elasticsearch import Elasticsearch
from elasticsearch.exceptions import NotFoundError
from dotenv import find_dotenv, load_dotenv
import os
import uuid
import base64
import json
from datetime import datetime



# Load environment from .env file
env_elastic = find_dotenv(".env")
load_dotenv(env_elastic)

# Config Firebase
config = {
    "apiKey": os.environ.get("apiKey"),
    "authDomain": os.environ.get("authDomain"),
    "databaseURL": os.environ.get("databaseURL"),
    "projectId": os.environ.get("projectId"),
    "storageBucket": os.environ.get("storageBucket"),
    "messagingSenderId": os.environ.get("messagingSenderId"),
    "appId": os.environ.get("appId"),
    "measurementId": os.environ.get("measurementId"),
    "serviceAccount": os.environ.get("serviceAccount")
}

# Initialize Firebase
firebase = pyrebase.initialize_app(config)
auth = firebase.auth()

# Initialize Flask
app = Flask(__name__)
app.secret_key = 'secret'  # replace with your own secret key

# Connect to Elastic search cloud
es = Elasticsearch(
    cloud_id=os.environ.get("cloud_id"),
    basic_auth=(os.environ.get("elastic_username"), os.environ.get("elastic_password"))
)
# Directory to store the images locally (we can remove this later since we will store the image in elastic search)
IMAGES_DIR = "./wasteimages/"



# Main Homepage
@app.route('/', methods=['GET', 'POST'])
def index():
    return render_template('index.html')

######### API ENDPOINTS FOR AUTHENTICATION ##########
# Authentication API endpoinrs - LOGIN
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        try:
            user = auth.sign_in_with_email_and_password(email, password)
            token = user['idToken']
            #print(token)
            session['user'] = email
            session['token'] = token
            return jsonify({'status': 'success', 'username': email, 'token': token})
        except:
            return jsonify({'status': 'failure', 'message': 'Invalid credentials'}), 401
    return render_template('login.html')

# Authentication API endpoinrs - LOGOUT
@app.route('/logout', methods=['POST'])
def logout():
    if 'user' in session:
        del session['user']
    if 'token' in session:
        del session['token']
    return jsonify({'status': 'success', 'message': 'User logged out successfully'})
    
# Authentication API endpoinrs - REGISTER
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        try:
            auth.create_user_with_email_and_password(email, password)
            return redirect(url_for('login'))
        except Exception as e:
            error_message = "Invalid Email or Password. Please try again."
            return render_template('register.html', error=error_message)
    return render_template('register.html')

    
# Direct to Profile page
@app.route("/profile/<username>+<token>")
def profile(username, token):
    if(token == session['token'] and username == session['user']):
        print("Correct Token")
        return render_template('profile.html', username=username.split('@')[0], email=username)
    else:
        return render_template('login.html')
    

######### API ENDPOINTS FOR USER PROFILE ##########
# POST request to predict image by uploading the image file
@app.route("/predict/image", methods=["POST"])
def predict_api():
    # Check if the user is logged in (by checking the session)
    if 'user' not in session:
        return jsonify({"message": "User is not authenticated!"}), 401
    
    file = request.files["file"]
    username = session['user']
    # Check if images are in the correct format
    extension = file.filename.split(".")[-1] in ("jpg", "jpeg", "png")
    if not extension:
        return jsonify({"message": "Image must be in jpg, jpeg, or png format!"}), 400
    
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
    # Check if the user is logged in (by checking the session)
    if 'user' not in session:
        return jsonify({"message": "User is not authenticated!"}), 401
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


# GET waste type information given waste type
@app.route("/waste/<waste_type>", methods=["GET"])
def get_waste_type_info(waste_type):
    # Check if the user is logged in (by checking the session)
    if 'user' not in session:
        return jsonify({"message": "User is not authenticated!"}), 401
    
    try:
        # Search for waste_type info 
        res = es.search(
            index='wasteinfo',
            query={
                    "bool": {
                        "should": [
                            {
                                "regexp": {
                                    "waste_type": {
                                        "value": f".*{waste_type}.*",
                                        "flags": "ALL",
                                        "case_insensitive": True
                                    }
                                }
                            }
                        ]
                    }
            }
        )
        # Store the results
        # Check if a matching document was found
        if res['hits']['total']['value'] > 0:
            source = res['hits']['hits'][0]['_source']
            return jsonify(source)
        else:
            return jsonify({"error": f"{waste_type} was not found in the waste types data."}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# POST request that returns drop-off locations based on SiteType and Zipcode
@app.route("/searchByZipCodeSiteType", methods=["POST"])
def search_location():
    # Check if the user is logged in (by checking the session)
    if 'user' not in session:
        return jsonify({"message": "User is not authenticated!"}), 401
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
    # Check if the user is logged in (by checking the session)
    if 'user' not in session:
        return jsonify({"message": "User is not authenticated!"}), 401
    
    # Check if the user is logged in (by checking the session)
    if 'user' not in session:
        return jsonify({"message": "User is not authenticated!"}), 401
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
    # Check if the user is logged in (by checking the session)
    if 'user' not in session:
        return jsonify({"message": "User is not authenticated!"}), 401
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
    # Check if the user is logged in (by checking the session)
    if 'user' not in session:
        return jsonify({"message": "User is not authenticated!"}), 401
    # Get the data from the form data in the POST request
    username = session["user"]
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
                            {"term": {"username": username.split("@")[0]}}   # Filter by username and field   
                        ],
                        "must": [
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
            counts_dict[value] = counts_dict.get(value, 0) + 1
    return counts_dict

# GET request to get number of unique values within a field name based on username (Portfolio Tab)
@app.route("/findNumUniqueValuesWithinFieldByUsername", methods=["GET"])
def get_num_unique():
    # Check if the user is logged in (by checking the session)
    if 'user' not in session:
        return jsonify({"message": "User is not authenticated!"}), 401
    # Get the inputs
    username = session["user"]
    field_name = request.args.get("field_name")

    # Validate inputs
    if not username or not field_name:
        return jsonify({"error": "Please specify both username and field_name!"}), 404
    # Validate field_name:
    accepted_field_name = ["image_id","waste_type","image_filename"]

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
                            {"match": {"username": username.split("@")[0]}}
                    ]}
            }, 
            aggs={
                    "unique_values": {
                        "terms": {"field": f"{field_name}"}
                    }
            }
        )

        # Check if result has been found
        unique_values = res["aggregations"]["unique_values"]
        if not unique_values:
            return jsonify({"error": "Data not found!"}), 404

        # Store the results 
        #source_list = [hit["_source"] for hit in hits]
        
        # Extract the chosen field and count unique values
        #count_dict = count_unique_values_by_field(source_list,str(field_name))

        # Use dict to store result and format it
        output_dict = {}
        for item in unique_values["buckets"]:
            output_dict[item["key"]] = item["doc_count"]

        # Format the result as a dictionary
        return jsonify(output_dict)

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    

# GET request to retrieve alll waste classified items for a given username (Portfolio Tab)
@app.route("/findClassifiedWasteByUsername", methods=["GET"])
def get_waste_classified():
     # Check if the user is logged in (by checking the session)
    if 'user' not in session:
        return jsonify({"message": "User is not authenticated!"}), 401
    # Get the inputs
    username = session["user"]

    try:
        # Perform the Elasticsearch search
        res = es.search(
                index='wasteclassified',
                source_excludes=["image_binary","image_path","username"],   # Exclude some fields
                size=1000,
                query={
                    "bool": {
                        "filter": [
                            {"term": {"username": username.split("@")[0]}}
                        ]}
            }
        )

        # Extract the hits from the response
        hits = res["hits"]["hits"]

        # Check if there are any hits
        if not hits:
            return jsonify({"message": "No waste classified items found for the given username."}), 404

        # Store results
        classified_items = [hit["_source"] for hit in hits]
        return jsonify(classified_items), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(host="localhost", port=5678)