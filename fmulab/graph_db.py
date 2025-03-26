"""
Neo4j database connection and query execution for FMU simulation
Based on original graph_query.py get_graphDB_driver function
"""
import logging
import os
import json
from neo4j import GraphDatabase, time


class Neo4jConnection:
    def __init__(self, uri=None, username=None, password=None, database="neo4j"):
        """
        Initialize the Neo4j connection with credentials
        """
        from django.conf import settings
        self.uri = uri if uri is not None else settings.NEO4J_URI
        self.username = username if username is not None else settings.NEO4J_USERNAME
        self.password = password if password is not None else settings.NEO4J_PASSWORD
        self.database = database if database is not None else settings.NEO4J_DATABASE

        self.enable_user_agent = getattr(settings, "ENABLE_USER_AGENT", False)
        self.user_agent = getattr(settings, "NEO4J_USER_AGENT", None)

        # For debugging
        logging.info(f"Neo4jConnection initialized with URI: {self.uri}")
        logging.info(f"Using username: {self.username}")
        logging.info(f"Using database: {self.database}")
        self.driver = None

    def connect(self):
        """
        Creates and returns a Neo4j database driver instance configured for Aura if needed
        """
        try:
            # Clean up URI - important for Aura connections
            uri = self.uri.strip()
            logging.info(f"Attempting to connect to the Neo4j database at {uri}")
            logging.info(f"Using username: {self.username}")
            logging.info(f"Using database: {self.database}")

            # Create the driver with appropriate settings
            if self.enable_user_agent and self.user_agent:
                self.driver = GraphDatabase.driver(
                    uri,
                    auth=(self.username, self.password),
                    database=self.database,
                    user_agent=self.user_agent
                )
            else:
                self.driver = GraphDatabase.driver(
                    uri,
                    auth=(self.username, self.password),
                    database=self.database
                )

            logging.info("Connection to Neo4j successful")
            return self.driver

        except Exception as e:
            error_message = f"Failed to connect to Neo4j at {uri}. Error: {str(e)}"
            logging.error(error_message, exc_info=True)
            return None

    def close(self):
        """Close the Neo4j connection"""
        if self.driver:
            self.driver.close()

    def execute_query(self, query, params=None):
        """
        Executes a specified query using the Neo4j driver with proper error handling.

        Returns:
        tuple: Contains records, summary of the execution, and keys of the records.
        """
        if not self.driver:
            self.connect()

        if self.driver is None:
            raise Exception("Failed to establish Neo4j connection. Check credentials and connection.")

        try:
            # For newer Neo4j versions (4.0+) use execute_query method
            if hasattr(self.driver, 'execute_query'):
                # This returns a tuple of (records, summary, keys)
                return self.driver.execute_query(query, **(params or {}))
            else:
                # Fallback to session.run for older Neo4j versions
                with self.driver.session(database=self.database) as session:
                    result = session.run(query, params or {})
                    records = list(result)
                    summary = result.consume()
                    keys = result.keys() if records else []
                    return records, summary, keys

        except Exception as e:
            error_message = f"Failed to execute query: {str(e)}"
            logging.error(error_message, exc_info=True)
            raise Exception(error_message)

    def get_completed_documents(self):
        """
        Retrieves the names of all documents with the status 'Completed' from the database.
        Based on the original get_completed_documents function.
        """
        docs_query = "MATCH(node:Document {status:'Completed'}) RETURN node"

        try:
            logging.info("Executing query to retrieve completed documents.")
            records, summary, keys = self.execute_query(docs_query)
            logging.info(f"Query executed successfully, retrieved {len(records)} records.")

            # Extract document names based on Neo4j driver version and response format
            if hasattr(records[0], "get") and "node" in records[0]:
                # New Neo4j driver format
                documents = [record["node"]["fileName"] for record in records]
            else:
                # Handle different format or older Neo4j driver
                documents = [record[0]["fileName"] for record in records]

            logging.info("Document names extracted successfully.")
            return documents

        except Exception as e:
            logging.error(f"An error occurred retrieving documents: {e}")
            return []

    def get_graph_for_documents(self, document_names, chunk_limit=50):
        """
        Get a graph representation for specified documents.
        Based on the original get_graph_results function.
        """
        try:
            logging.info(f"Starting graph query process for documents: {document_names}")

            # Convert document_names to the expected format
            if isinstance(document_names, str):
                # Handle case where it might be a JSON string
                try:
                    document_names = json.loads(document_names)
                except json.JSONDecodeError:
                    document_names = [document_names]

            # Make sure document_names is a list of strings
            document_names = list(map(str.strip, document_names))

            # Use the original GRAPH_QUERY from constants.py with formatting
            from .config import GRAPH_QUERY
            query = GRAPH_QUERY.format(graph_chunk_limit=chunk_limit)

            # Execute the query
            records, summary, keys = self.execute_query(query, {
                "document_names": document_names
            })

            # Process results using helper functions
            document_nodes = self.extract_node_elements(records)
            document_relationships = self.extract_relationships(records)

            logging.info(f"Number of nodes: {len(document_nodes)}")
            logging.info(f"Number of relations: {len(document_relationships)}")

            result = {
                "nodes": document_nodes,
                "relationships": document_relationships
            }

            logging.info(f"Query process completed successfully")
            return result

        except Exception as e:
            logging.error(f"Error retrieving graph: {str(e)}")
            return {"nodes": [], "relationships": []}

    def process_node(self, node):
        """
        Processes a node from a Neo4j database, extracting its ID, labels, and properties,
        while omitting certain properties like 'embedding' and 'text'.
        """
        try:
            labels = set(node.labels)
            labels.discard("__Entity__")
            if not labels:
                labels.add('*')

            node_element = {
                "element_id": node.element_id,
                "labels": list(labels),
                "properties": {}
            }

            for key in node:
                if key in ["embedding", "text", "summary"]:
                    continue
                value = node.get(key)
                if isinstance(value, time.DateTime):
                    node_element["properties"][key] = value.isoformat()
                else:
                    node_element["properties"][key] = value

            return node_element
        except Exception as e:
            logging.error(f"An unexpected error occurred while processing the node: {str(e)}")
            return {"element_id": "unknown", "labels": [], "properties": {}}

    def extract_node_elements(self, records):
        """
        Extracts and processes unique nodes from a list of records, avoiding
        duplication by tracking seen element IDs.
        """
        node_elements = []
        seen_element_ids = set()

        try:
            for record in records:
                nodes = record.get("nodes", [])
                if not nodes:
                    continue

                for node in nodes:
                    if node.element_id in seen_element_ids:
                        continue
                    seen_element_ids.add(node.element_id)
                    node_element = self.process_node(node)
                    node_elements.append(node_element)

            return node_elements
        except Exception as e:
            logging.error(f"An error occurred while extracting node elements: {str(e)}")
            return []

    def extract_relationships(self, records):
        """
        Extracts and processes relationships from a list of records, ensuring that
        each relationship is processed only once by tracking seen element IDs.
        """
        all_relationships = []
        seen_element_ids = set()

        try:
            for record in records:
                relationships = []
                relations = record.get("rels", [])
                if not relations:
                    continue

                for relation in relations:
                    if relation.element_id in seen_element_ids:
                        continue
                    seen_element_ids.add(relation.element_id)

                    try:
                        nodes = relation.nodes
                        if len(nodes) < 2:
                            logging.warning(f"Relationship with ID {relation.element_id} does not have two nodes.")
                            continue

                        relationship = {
                            "element_id": relation.element_id,
                            "type": relation.type,
                            "start_node_element_id": self.process_node(nodes[0])["element_id"],
                            "end_node_element_id": self.process_node(nodes[1])["element_id"],
                        }
                        relationships.append(relationship)

                    except Exception as inner_e:
                        logging.error(f"Failed to process relationship with ID {relation.element_id}: {inner_e}")

                all_relationships.extend(relationships)

            return all_relationships
        except Exception as e:
            logging.error(f"An error occurred while extracting relationships: {str(e)}")
            return []