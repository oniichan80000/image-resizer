import boto3
import os
import io
from PIL import Image
import urllib.parse
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize S3 client
s3_client = boto3.client('s3')

# Get destination bucket name from environment variable
DESTINATION_BUCKET = os.environ.get('DESTINATION_BUCKET_NAME', 'imageresizer-imageprocessed')
DEFAULT_MAX_SIZE = 256
MIN_RESIZE_DIMENSION = 64
MAX_RESIZE_DIMENSION = 4096
def lambda_handler(event, context):
    """
    Handles S3 put events, downloads image, resizes if needed, uploads to destination.
    """
    print("Received event:", event) # Log the incoming event for debugging

    try:
        # 1. Get Bucket and Key from the event
        record = event['Records'][0]
        source_bucket = record['s3']['bucket']['name']
        # Object key may have spaces or special characters, need to unquote
        source_key = urllib.parse.unquote_plus(record['s3']['object']['key'])

        print(f"Source Bucket: {source_bucket}")
        print(f"Source Key: {source_key}")

        # Prevent infinite loops: check if source and destination are the same
        # or if the event is from the destination bucket (if using prefixes)
        # This simple check assumes different bucket names. Adjust if using prefixes.
        if source_bucket == DESTINATION_BUCKET:
             print("Source and destination buckets are the same, skipping processing.")
             return {'statusCode': 200, 'body': 'Skipped (source == destination)'}

        # 2. Download the image from Source S3
        try:
            response = s3_client.get_object(Bucket=source_bucket, Key=source_key)
            image_data = response['Body'].read()
            content_type = response.get('ContentType', 'image/jpeg') # Default to jpeg if not specified
            metadata = response.get('Metadata', {}) # Get object metadata
            print(f"Downloaded {source_key} from {source_bucket}. ContentType: {content_type}")
        except Exception as e:
            print(f"Error downloading from S3: {e}")
            raise e # Fail the function execution

        # --- Determine Max Size ---
        max_size = DEFAULT_MAX_SIZE # Start with default
        max_size_str = metadata.get('max-dimension') # Metadata keys are lowercased by boto3/S3

        if max_size_str:
            try:
                parsed_size = int(max_size_str)
                # Validate against resize limits
                if MIN_RESIZE_DIMENSION <= parsed_size <= MAX_RESIZE_DIMENSION:
                     max_size = parsed_size
                     logger.info(f"Using custom max dimension from metadata: {max_size}px")
                else:
                     logger.warning(f"Invalid custom dimension '{max_size_str}' in metadata (out of range {MIN_RESIZE_DIMENSION}-{MAX_RESIZE_DIMENSION}). Using default {DEFAULT_MAX_SIZE}px.")
            except ValueError:
                logger.warning(f"Non-integer custom dimension '{max_size_str}' in metadata. Using default {DEFAULT_MAX_SIZE}px.")
        else:
             logger.info(f"No custom dimension in metadata. Using default {DEFAULT_MAX_SIZE}px.")
        # --------------------------

        # 3. Image Resizing Logic
        with Image.open(io.BytesIO(image_data)) as img:
             # handle potential image loading errors
            try:
                img.verify() # Verify image data integrity if possible
                # Re-open after verify
                img = Image.open(io.BytesIO(image_data))
            except Exception as img_err:
                logger.error(f"Invalid image format or error opening image {source_key}: {img_err}", exc_info=True)
                # Optional: You could try to put the original object in destination or just fail
                raise ValueError(f"Could not process image file: {source_key}") from img_err

            original_width, original_height = img.size
            print(f"Original dimensions: {original_width}x{original_height}")

            if original_width <= max_size and original_height <= max_size:
                logger.info(f"Image dimensions ({original_width}x{original_height}) are within target max size ({max_size}px). No resizing needed.")
                output_data = io.BytesIO(image_data) # Use original data
            else:
                logger.info(f"Resizing required to fit max dimension {max_size}px.")
                # Use thumbnail to resize inplace maintaining aspect ratio
                img.thumbnail((max_size, max_size))
                resized_width, resized_height = img.size
                print(f"Resized dimensions: {resized_width}x{resized_height}")

                # Save resized image to a buffer
                buffer = io.BytesIO()
                # Preserve original format if possible, else default (e.g., PNG for transparency)
                img_format = img.format if img.format else 'PNG'
                if img_format == 'JPEG':
                   # Handle potential lack of transparency in JPEG
                   if img.mode in ("RGBA", "P"):
                       img = img.convert("RGB")
                   img.save(buffer, format='JPEG', quality=90) # Control JPEG quality
                else:
                   img.save(buffer, format=img_format)

                buffer.seek(0)
                output_data = buffer
                print(f"Image resized and saved to buffer in {img_format} format.")

        # 4. Upload the resulting file back to Destination S3
        # Use the same key name in the destination bucket
        destination_key = source_key
        try:
            s3_client.put_object(
                Bucket=DESTINATION_BUCKET,
                Key=destination_key,
                Body=output_data,
                ContentType=content_type # Use the original or determined content type
            )
            print(f"Successfully uploaded {destination_key} to {DESTINATION_BUCKET}")
        except Exception as e:
            print(f"Error uploading to Destination S3: {e}")
            raise e # Fail the function execution

        return {
            'statusCode': 200,
            'body': f'Successfully processed {source_key} from {source_bucket}'
        }

    except Exception as e:
        print(f"Error processing file {source_key} from bucket {source_bucket}: {e}")
        # Log the full traceback for debugging
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'body': f'Error processing file: {e}'
        }