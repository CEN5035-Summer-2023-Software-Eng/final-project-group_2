import os
import uuid
import base64
import json
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
        # Save the image locally
        image.save(image_path)

        # Convert the PIL image to bytes
        image_bytes = BytesIO()
        image.save(image_bytes, format="JPEG")
        image_bytes = image_bytes.getvalue()

        # Convert the bytes to base64 encoding
        base64_image = base64.b64encode(image_bytes).decode("utf-8")
        
        # Information that we will be storing in the elastic cloud (missing username variable)
        doc = {
            "image_id": image_id,
            "waste_type": waste_type,
            "confidence_score": confidence_score,
            "image_filename": file.filename,
            "image_path": image_path,
            "image_binary": base64_image
        }
        # Ingest the data
        es.index(index="wasteclassified", document=doc)
        # Send results as json format (only including id, waste type, and confidence score)
        return jsonify({"image_id": image_id, "waste_type": waste_type, "confidence_score": confidence_score}), 200

    except Exception as e:
        return jsonify({"message": "Prediction failed. Please try again."}), 500

# Display the image using image_id
@app.route("/display/<image_id>")
def display_image(image_id):
    try:
        # Retrieve the image from Elasticsearch based on image_id
        res = es.search(
            index='wasteclassified',
            query={
                'match': {'image_id': image_id}
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
        return jsonify({"error": "Failed to retrieve the image."}), 500


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
        return jsonify({"error": f"'{waste_type}' was not found in the waste types data."}), 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
