"""
Script to create required OpenSearch indexes for our transcription application.
"""
import os
from dotenv import load_dotenv
from opensearchpy import OpenSearch, RequestsHttpConnection

# Load environment variables
load_dotenv()

OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST", "localhost")
OPENSEARCH_PORT = int(os.getenv("OPENSEARCH_PORT", "9200"))
OPENSEARCH_USER = os.getenv("OPENSEARCH_USER", "admin")
OPENSEARCH_PASSWORD = os.getenv("OPENSEARCH_PASSWORD", "admin")

# OpenSearch indexes
TRANSCRIPT_INDEX = "transcripts"
SPEAKER_INDEX = "speakers"

def create_client():
    """Create and return an OpenSearch client."""
    client = OpenSearch(
        hosts=[{'host': OPENSEARCH_HOST, 'port': OPENSEARCH_PORT}],
        http_auth=(OPENSEARCH_USER, OPENSEARCH_PASSWORD) if OPENSEARCH_USER and OPENSEARCH_PASSWORD else None,
        use_ssl=False,
        verify_certs=False,
        connection_class=RequestsHttpConnection
    )
    return client

def create_transcript_index(client):
    """Create the transcript index for searching transcript segments."""
    index_body = {
        'settings': {
            'index': {
                'number_of_shards': 1,
                'number_of_replicas': 0
            },
            'analysis': {
                'analyzer': {
                    'default': {
                        'tokenizer': 'standard',
                        'filter': ['lowercase', 'stop', 'porter_stem']
                    }
                }
            }
        },
        'mappings': {
            'properties': {
                'segment_id': {'type': 'keyword'},
                'file_id': {'type': 'keyword'},
                'user_id': {'type': 'keyword'},
                'speaker_id': {'type': 'keyword'},
                'speaker_name': {'type': 'keyword'},
                'text': {'type': 'text', 'analyzer': 'default'},
                'text_vector': {'type': 'float', 'index': False},  # Store embedding as array of floats
                'start_time': {'type': 'float'},
                'end_time': {'type': 'float'},
                'confidence': {'type': 'float'},
                'created_at': {'type': 'date'},
                'updated_at': {'type': 'date'}
            }
        }
    }
    
    # Check if index exists
    if not client.indices.exists(index=TRANSCRIPT_INDEX):
        print(f"Creating index: {TRANSCRIPT_INDEX}")
        client.indices.create(index=TRANSCRIPT_INDEX, body=index_body)
        print(f"Index {TRANSCRIPT_INDEX} created successfully")
    else:
        print(f"Index {TRANSCRIPT_INDEX} already exists")

def create_speaker_index(client):
    """Create the speaker index for storing speaker embeddings."""
    index_body = {
        'settings': {
            'index': {
                'number_of_shards': 1,
                'number_of_replicas': 0
            }
        },
        'mappings': {
            'properties': {
                'speaker_id': {'type': 'keyword'},
                'name': {'type': 'keyword'},
                'user_id': {'type': 'keyword'},
                'embedding': {'type': 'float', 'index': False},  # Store embedding as array of floats
                'file_ids': {'type': 'keyword'},
                'created_at': {'type': 'date'},
                'updated_at': {'type': 'date'}
            }
        }
    }
    
    # Check if index exists
    if not client.indices.exists(index=SPEAKER_INDEX):
        print(f"Creating index: {SPEAKER_INDEX}")
        client.indices.create(index=SPEAKER_INDEX, body=index_body)
        print(f"Index {SPEAKER_INDEX} created successfully")
    else:
        print(f"Index {SPEAKER_INDEX} already exists")

def main():
    # Create OpenSearch client
    client = create_client()
    
    # Check if OpenSearch is running
    try:
        health = client.cluster.health()
        print(f"OpenSearch cluster status: {health['status']}")
        
        # Create indexes
        create_transcript_index(client)
        create_speaker_index(client)
        
    except Exception as e:
        print(f"Error connecting to OpenSearch: {e}")

if __name__ == "__main__":
    main()
