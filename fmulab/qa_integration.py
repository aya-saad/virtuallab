"""
QA Integration module for connecting Neo4j with LLMs
"""
import logging
import json
import os
from datetime import datetime
from .graph_db import Neo4jConnection
from .llm_integration import get_llm_provider

# Constants for prompt engineering
SYSTEM_PROMPT = """
You are an AI-powered question-answering agent. Your task is to provide accurate and comprehensive responses to user queries based on the given context and available resources.

### Response Guidelines:
1. **Direct Answers**: Provide clear and thorough answers to the user's queries. Avoid speculative responses.
2. **Use Context**: Use only the information from the context provided below.
3. **Acknowledge Unknowns**: Clearly state if an answer is unknown. Do not make up information.
4. **Keep Responses Concise**: Aim for clarity and completeness within 4-5 sentences unless more detail is needed.
5. **Professional Tone**: Maintain a professional and informative tone. Be friendly and approachable.

### Context:
{}

IMPORTANT: DO NOT ANSWER FROM YOUR KNOWLEDGE BASE. USE ONLY THE CONTEXT PROVIDED.
"""


class QAIntegration:
    """QA Pipeline integrating Neo4j and LLMs"""

    def __init__(self, neo4j_connection=None, llm_provider=None):
        """Initialize the QA pipeline"""
        self.neo4j = neo4j_connection or Neo4jConnection()
        if not self.neo4j.driver:
            self.neo4j.connect()

        self.llm = llm_provider or get_llm_provider()
        self.chat_history = {}  # Session ID -> list of messages

    def get_documents(self):
        """Get list of available documents"""
        return self.neo4j.get_completed_documents()

    def _format_context_from_chunks(self, chunks):
        """Format chunks into context for LLM prompt"""
        formatted_chunks = []

        for i, chunk in enumerate(chunks):
            formatted_chunk = f"Document {i + 1}:\n{chunk.get('text', '')}\n"
            formatted_chunks.append(formatted_chunk)

        return "\n\n".join(formatted_chunks)

    def retrieve_chunks(self, query, document_names=None, limit=5):
        """Retrieve relevant chunks from Neo4j based on query"""
        try:
            # Basic semantic search query - in production, use vector similarity
            search_query = """
            MATCH (d:Document)
            WHERE d.fileName IN $document_names
            MATCH (d)<-[:PART_OF]-(c:Chunk)
            WHERE c.text CONTAINS $query_text
            RETURN c
            LIMIT $limit
            """

            if not document_names:
                # If no documents specified, search all documents
                search_query = """
                MATCH (d:Document)<-[:PART_OF]-(c:Chunk)
                WHERE c.text CONTAINS $query_text
                RETURN c
                LIMIT $limit
                """

            params = {
                "query_text": query,
                "limit": limit
            }

            if document_names:
                params["document_names"] = document_names

            records, _ = self.neo4j.execute_query(search_query, params)

            chunks = []
            for record in records:
                chunk = record["c"]
                chunks.append({
                    "id": chunk.get("id", ""),
                    "text": chunk.get("text", ""),
                    "source": record.get("fileName", "Unknown")
                })

            return chunks

        except Exception as e:
            logging.error(f"Error retrieving chunks: {str(e)}")
            return []

    def get_chat_response(self, query, session_id=None, document_names=None):
        """Get a response to the user query"""
        try:
            # Initialize or get chat history
            if not session_id:
                session_id = f"session_{datetime.now().timestamp()}"

            if session_id not in self.chat_history:
                self.chat_history[session_id] = []

            # Add the query to chat history
            self.chat_history[session_id].append({"role": "user", "content": query})

            # Retrieve relevant chunks
            chunks = self.retrieve_chunks(query, document_names)

            if not chunks:
                no_info_response = "I couldn't find any relevant information to answer your question."
                self.chat_history[session_id].append({"role": "assistant", "content": no_info_response})
                return {
                    "message": no_info_response,
                    "sources": [],
                    "session_id": session_id
                }

            # Format chunks into context
            context = self._format_context_from_chunks(chunks)

            # Generate the prompt with context
            prompt = SYSTEM_PROMPT.format(context) + f"\nQuestion: {query}"

            # Get response from LLM
            response = self.llm.generate(prompt)

            # Add response to chat history
            self.chat_history[session_id].append({"role": "assistant", "content": response})

            # Extract sources for attribution
            sources = list(set([chunk.get("source", "Unknown") for chunk in chunks]))

            return {
                "message": response,
                "sources": sources,
                "session_id": session_id
            }

        except Exception as e:
            logging.error(f"Error in QA pipeline: {str(e)}")
            error_response = f"I'm sorry, but I encountered an error while processing your question: {str(e)}"

            if session_id in self.chat_history:
                self.chat_history[session_id].append({"role": "assistant", "content": error_response})

            return {
                "message": error_response,
                "sources": [],
                "session_id": session_id
            }

    def close(self):
        """Close connections"""
        if self.neo4j:
            self.neo4j.close()