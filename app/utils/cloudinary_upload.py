#C:\Users\Vladimir\Documents\Sistema tickets\app\utils\cloudinary_upload.py

import cloudinary
import cloudinary.uploader
from flask import current_app

def config_cloudinary():
    cloudinary.config(
        cloud_name=current_app.config['CLOUDINARY_CLOUD_NAME'],
        api_key=current_app.config['CLOUDINARY_API_KEY'],
        api_secret=current_app.config['CLOUDINARY_API_SECRET']
    )

def upload_image_to_cloudinary(image_file):
    config_cloudinary()
    result = cloudinary.uploader.upload(image_file)
    return result.get('secure_url')
