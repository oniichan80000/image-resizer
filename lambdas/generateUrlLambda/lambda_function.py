import boto3
import os
import json
import logging
import uuid
import re
from botocore.config import Config

# Configure logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# --- Configuration ---
# Get configuration from environment variables with defaults
REGION = os.environ.get('AWS_REGION', 'us-east-1') # Replace default with your specific region if needed
UPLOAD_BUCKET = os.environ.get('UPLOAD_BUCKET_NAME', 'imageresizer-imageuploads')

# Initialize S3 client
s3_client = boto3.client('s3', region_name=REGION, config=Config(signature_version='s3v4'))

# Define reasonable limits for custom dimension
MIN_DIMENSION = 64
MAX_DIMENSION = 4096 # (adjust as needed)


def lambda_handler(event, context):
    """
    Generates an S3 presigned URL for uploading a file.
    Expects filename and contentType in the event body for POST requests.
    """
    logger.info(f"Received event: {json.dumps(event)}")

    # Default values
    # Generate a unique key to prevent collisions and add basic structure
    object_key = f"{uuid.uuid4()}"
    content_type = 'image/jpeg' # Default content type

    custom_dimension = None # Variable to hold validated custom dimension

    # Try to get filename and content type from the request body (for POST)
    # Assumes API Gateway HTTP API payload format v2.0
    if 'body' in event and event.get('requestContext', {}).get('http', {}).get('method') == 'POST':
        try:
            body = json.loads(event['body'])
            filename = body.get('filename')
            req_content_type = body.get('contentType')
            req_max_dimension = body.get('maxDimension') # Get custom dimension from request


            if filename:
                 # Sanitize filename: remove potentially unsafe characters, limit length
                 safe_filename = re.sub(r'[^\w\.\-]', '', filename) # Allow word chars, dots, hyphens
                 safe_filename = safe_filename[:100] # Limit length
                 object_key = f"{uuid.uuid4()}-{safe_filename}" # Combine UUID and safe filename
                 logger.info(f"Using filename from body: {safe_filename}")

            if req_content_type:
                content_type = req_content_type
                logger.info(f"Using contentType from body: {content_type}")

            # --- Validate Custom Dimension ---
            if req_max_dimension is not None:
                try:
                    parsed_dimension = int(req_max_dimension)
                    if MIN_DIMENSION <= parsed_dimension <= MAX_DIMENSION:
                        custom_dimension = parsed_dimension # Store validated dimension
                        logger.info(f"Using custom max dimension from request: {custom_dimension}")
                    else:
                        logger.warning(f"Requested dimension {parsed_dimension} out of range ({MIN_DIMENSION}-{MAX_DIMENSION}). Ignoring.")
                except (ValueError, TypeError):
                     logger.warning(f"Invalid non-integer dimension '{req_max_dimension}' received. Ignoring.")
            # ---------------------------------
        except Exception as e:
            logger.warning(f"Error processing event body: {e}")

    # Parameters for the presigned URL
    presigned_params = {
        'Bucket': UPLOAD_BUCKET,
        'Key': object_key,
        'ContentType': content_type,
    }
    expires_in = 300  # URL expiration time in seconds (e.g., 5 minutes)

    # --- Add Metadata if custom dimension is valid ---
    if custom_dimension is not None:
        presigned_params['Metadata'] = {
            'max-dimension': str(custom_dimension) # Metadata values must be strings
        }
        logger.info(f"Adding metadata: {{'max-dimension': '{custom_dimension}'}}")
    # -----------------------------------------------

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
            # IMPORTANT: Add CORS headers matching frontend origin
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