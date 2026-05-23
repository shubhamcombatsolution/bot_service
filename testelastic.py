from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
import logging

class ElasticHandler:
    def __init__(self):
        self.index_name = "sample_index"
        self.es_url = "http://localhost:9200/"
        
        try:
            self.es = Elasticsearch(
                self.es_url,
                timeout=30,
                max_retries=3,
                retry_on_timeout=True
            )
        except Exception as e:
            logging.error(f"Error connecting to Elasticsearch: {e}")

    def create_index(self):
        try:
            # Define mapping with two columns
            mapping = {
                "mappings": {
                    "properties": {
                        "name": {"type": "text"},
                        "age": {"type": "integer"}
                    }
                }
            }

            # Create index if it doesn't exist
            if not self.es.indices.exists(index=self.index_name):
                self.es.indices.create(index=self.index_name, body=mapping)
                print(f"Index '{self.index_name}' created successfully")
            else:
                print(f"Index '{self.index_name}' already exists")
                
        except Exception as e:
            logging.error(f"Error creating index: {e}")

    def insert_records(self):
        try:
            # Sample records
            records = [
                {
                    "_index": self.index_name,
                    "_source": {
                        "name": "John Doe",
                        "age": 30
                    }
                },
                {
                    "_index": self.index_name,
                    "_source": {
                        "name": "Jane Smith",
                        "age": 25
                    }
                }
            ]

            # Bulk insert
            success, failed = bulk(self.es, records, raise_on_error=False)
            
            print(f"Successfully inserted {success} records")
            if failed:
                print(f"Failed to insert {len(failed)} records")

        except Exception as e:
            logging.error(f"Error inserting records: {e}")

# Usage example
if __name__ == "__main__":
    # Initialize handler
    handler = ElasticHandler()
    
    # Create index
    handler.create_index()
    
    # Insert records
    handler.insert_records()