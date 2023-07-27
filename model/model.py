
from pathlib import Path
import tensorflow as tf
from PIL import Image
import numpy as np
from io import BytesIO

# Initialize model version
__version__ = "0.1.0"
# Get current directory
BASE_DIR = Path(__file__).resolve(strict=True).parent
trained_model_path = f"{BASE_DIR}/trained_pipeline-{__version__}.h5"
# Image size
IMAGE_SHAPE = (256,256)
# Classes
classes = ['Electronics', 'Glass', 'Medical', 'Metal', 'Organic Waste', 'Paper and Cardboard', 'Plastic', 'Textiles', 'Wood']

model = None

# Load the trained model
def load_model():
    model = tf.keras.models.load_model(trained_model_path)
    print("Load the model ...")
    return model

# Predict the image
def tf_predict(image: Image.Image):
    # Check if model is loaded
    global model
    if model is None:
        model = load_model()

    # Convert image to array
    img_array = tf.keras.preprocessing.image.img_to_array(image.resize(IMAGE_SHAPE))
    img_array = tf.expand_dims(img_array, 0) 

    # Predict
    predictions = model.predict(img_array)
    # Get confidence score 
    rounded_max_prob = round(predictions[0][np.argmax(predictions)]*100, 2)

    #print(f"Prediction: {classes[np.argmax(predictions)]} with a {rounded_max_prob}% confidence")

    return classes[np.argmax(predictions)],rounded_max_prob

# Read image file using PIL
def read_imagefile(file) -> Image.Image:
    image = Image.open(BytesIO(file))
    return image
