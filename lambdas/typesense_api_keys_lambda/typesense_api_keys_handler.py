import os
import boto3
import typesense
import logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):

    logger.info('Getting all the parameters that should have been passed in event payload')
    typesense_key_generating_key_name = event["TypesenseKeyGeneratingKeyName"]
    new_typesense_key_name = event["NewTypesenseKeyName"]
    new_typesense_key_description = event["NewTypesenseKeyDescription"]
    new_typesense_key_actions = event["NewTypesenseKeyActions"].split(',')
    new_typesense_key_collections = event["NewTypesenseKeyCollections"].split(',')

    secretsmanager_client = boto3.client('secretsmanager')

    # Get typesense key-generating api key from secretsmanager
    # This should be the admin key, except for when the admin key is first being created.  In that case use the bootstrap key.
    logger.info('Getting Typesense Key for Generating a New Key')
    secretsmanager_resp = secretsmanager_client.get_secret_value(SecretId=typesense_key_generating_key_name)
    typesense_key_generating_key = secretsmanager_resp['SecretString']

    logger.info('Creating Typesense Client')
    typesense_client = typesense.Client({
        'api_key': typesense_key_generating_key,
        'nodes': [{
            'host': os.environ["TYPESENSE_ELASTIC_IP"],
            'port': os.environ["TYPESENSE_PORT"],
            'protocol': 'http',
        }],
        'connection_timeout_seconds': 2,
    })

    # Create a new api key 
    logger.info('Creating new Typesense API Key')
    typesense_resp = typesense_client.keys.create({
        "description": new_typesense_key_description,
        "actions": new_typesense_key_actions,
        "collections": new_typesense_key_collections,
    })
    new_key = typesense_resp["value"]

    logger.info('Storing New Key in SecretsManager')
    secretsmanager_resp = secretsmanager_client.create_secret(
        Name=new_typesense_key_name,
        SecretString=new_key,
        Description=new_typesense_key_description,
    )

    return dict(
        statusCode=201,
        body=str(secretsmanager_resp['Name'])
    )