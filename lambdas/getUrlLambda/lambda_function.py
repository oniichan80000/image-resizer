import boto3
import os
import json
import logging
from botocore.config import Config
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REGION = os.environ.get('AWS_REGION', 'us-east-1')
# IMPORTANT: Use DESTINATION bucket name here
PROCESSED_BUCKET = os.environ.get('PROCESSED_BUCKET_NAME', 'imageresizer-imageprocessed')

s3_client = boto3.client('s3',
                         region_name=REGION,
                         config=Config(signature_version='s3v4'))

def lambda_handler(event, context):
    logger.info(f"Received event: {json.dumps(event)}")

    # Expecting the object key as a query string parameter
    # e.g., /get-processed-url?key=uploads/some-uuid-image.jpg
    query_params = event.get('queryStringParameters', {})
    object_key = query_params.get('key')

    if not object_key:
        logger.error("Missing 'key' query string parameter.")
        return {
            'statusCode': 400,
            'headers': {'Access-Control-Allow-Origin': '*'}, # Include CORS
            'body': json.dumps({'message': "Missing 'key' query string parameter"})
        }

    logger.info(f"Requesting presigned GET URL for key: {object_key} in bucket: {PROCESSED_BUCKET}")

    presigned_params = {
        'Bucket': PROCESSED_BUCKET,
        'Key': object_key
    }
    expires_in = 300 # 5 minutes validity

    try:
        # Generate presigned URL for GET operation
        get_url = s3_client.generate_presigned_url(
            ClientMethod='get_object',
            Params=presigned_params,
            ExpiresIn=expires_in,
            HttpMethod='GET'
        )

        logger.info(f"Generated GET URL: {get_url}")

        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*', # Restrict in production
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'GET, OPTIONS'
            },
            'body': json.dumps({'processedUrl': get_url})
        }
    # Handle case where the object doesn't exist (yet or bad key)
    except ClientError as e:
         if e.response['Error']['Code'] == 'NoSuchKey':
             logger.warning(f"Object not found: {object_key} in bucket {PROCESSED_BUCKET}")
             return {
                 'statusCode': 404,
                 'headers': {'Access-Control-Allow-Origin': '*'}, # Include CORS
                 'body': json.dumps({'message': 'Processed object not found yet.'})
                 }
         else:
             logger.error(f"Error generating GET URL: {e}", exc_info=True)
             return {
                 'statusCode': 500,
                 'headers': {'Access-Control-Allow-Origin': '*'}, # Include CORS
                 'body': json.dumps({'message': 'Error generating processed URL', 'error': str(e)})
             }
    except Exception as e:
        logger.error(f"Error generating GET URL: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': {'Access-Control-Allow-Origin': '*'}, # Include CORS
            'body': json.dumps({'message': 'Error generating processed URL', 'error': str(e)})
        }