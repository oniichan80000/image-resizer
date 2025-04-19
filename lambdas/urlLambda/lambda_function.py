import boto3
import os
import json
import logging
import uuid
import re

# Configure logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# --- Configuration ---
# Get configuration from environment variables with defaults
REGION = os.environ.get('AWS_REGION', 'us-east-1') # Replace default with your specific region if needed
UPLOAD_BUCKET = os.environ.get('UPLOAD_BUCKET_NAME', 'imageresizer-imageuploads') # Replace with your source bucket

# Initialize S3 client
s3_client = boto3.client('s3', region_name=REGION, config=boto3.Config(signature_version='s3v4'))

def lambda_handler(event, context):
    """
    Generates an S3 presigned URL for uploading a file.
    Expects filename and contentType in the event body for POST requests.
    """
    logger.info(f"Received event: {json.dumps(event)}")

    # Default values
    # Generate a unique key to prevent collisions and add basic structure
    object_key = f"uploads/{uuid.uuid4()}"
    content_type = 'image/jpeg' # Default content type

    # Try to get filename and content type from the request body (for POST)
    # Assumes API Gateway HTTP API payload format v2.0
    if 'body' in event and event.get('requestContext', {}).get('http', {}).get('method') == 'POST':
        try:
            body = json.loads(event['body'])
            filename = body.get('filename')
            req_content_type = body.get('contentType')

            if filename:
                 # Sanitize filename: remove potentially unsafe characters, limit length
                 safe_filename = re.sub(r'[^\w\.\-]', '', filename) # Allow word chars, dots, hyphens
                 safe_filename = safe_filename[:100] # Limit length
                 object_key = f"uploads/{uuid.uuid4()}-{safe_filename}" # Combine UUID and safe filename
                 logger.info(f"Using filename from body: {safe_filename}")

            if req_content_type:
                content_type = req_content_type
                logger.info(f"Using contentType from body: {content_type}")

        except json.JSONDecodeError as e:
            logger.warning(f"Could not parse event body as JSON or extract details: {e}")
        except Exception as e:
            logger.warning(f"Error processing event body: {e}")

    # Parameters for the presigned URL
    presigned_params = {
        'Bucket': UPLOAD_BUCKET,
        'Key': object_key,
        'ContentType': content_type,
        # 'Metadata': {'user-id': 'example-user'} # Optional: Add metadata if needed
    }
    expires_in = 300  # URL expiration time in seconds (e.g., 5 minutes)

    try:
        # Generate the presigned URL for PUT operation
        presigned_url = s3_client.generate_presigned_url(
            ClientMethod='put_object',
            Params=presigned_params,
            ExpiresIn=expires_in,
            HttpMethod='PUT' # Specify the HTTP method the URL is valid for
        )

        logger.info(f"Generated presigned URL: {presigned_url}")
        logger.info(f"Object Key: {object_key}")

        response_body = {
            'uploadUrl': presigned_url,
            'key': object_key # Send the key back to the frontend
        }

        return {
            'statusCode': 200,
            # IMPORTANT: Add CORS headers matching your frontend origin
            'headers': {
                # Adjust '*' to your specific frontend URL in production for security
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'POST, OPTIONS' # Allowed methods for API Gateway endpoint
            },
            'body': json.dumps(response_body)
        }

    except Exception as e:
        logger.error(f"Error generating presigned URL: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': {
                # Also include CORS header in error responses
                'Access-Control-Allow-Origin': '*',
            },
            'body': json.dumps({'message': 'Error generating upload URL', 'error': str(e)})
        }