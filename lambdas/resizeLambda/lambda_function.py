import boto3
import os
import io
from PIL import Image
import urllib.parse

# Initialize S3 client
s3_client = boto3.client('s3')

# Get destination bucket name from environment variable
DESTINATION_BUCKET = os.environ.get('DESTINATION_BUCKET_NAME', 'imageresizer-imageprocessed')
MAX_SIZE = 256

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
            print(f"Downloaded {source_key} from {source_bucket}. ContentType: {content_type}")
        except Exception as e:
            print(f"Error downloading from S3: {e}")
            raise e # Fail the function execution

        # 3. Image Resizing Logic using Pillow
        with Image.open(io.BytesIO(image_data)) as img:
            original_width, original_height = img.size
            print(f"Original dimensions: {original_width}x{original_height}")

            # Check if resizing is needed
            if original_width > MAX_SIZE or original_height > MAX_SIZE:
                print("Resizing required.")
                # Calculate new dimensions maintaining aspect ratio
                if original_width > original_height:
                    new_width = MAX_SIZE
                    new_height = int(original_height * MAX_SIZE / original_width)
                else:
                    new_height = MAX_SIZE
                    new_width = int(original_width * MAX_SIZE / original_height)

                # Pillow's thumbnail modifies in place and maintains aspect ratio
                # It ensures *neither* dimension exceeds the provided size tuple.
                img.thumbnail((MAX_SIZE, MAX_SIZE))
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

            else:
                # No resizing needed, use original data
                print("No resizing needed.")
                output_data = io.BytesIO(image_data) # Use original data in a BytesIO object

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