"""
    This contains the ChatService
"""

import logging
import json
from groq import Groq

from services.postgres_searcher import PostgresSearcher
from config.main import config
from models.product import Product

logger = logging.getLogger(__name__)

PROMPT = """
You are a customer service representative for an online store.
You help customers find products they are looking for, and recommend products based on their needs.
You must use tool `search_products` to search for products based on the search query.

- Always output well formatted markdown text.
- Use the `search_products` tool to search for products based on the search query.
- Keep your answers concise and to the point. Don't overwhelm the user with too much information.
"""


class ChatService:
    """
    This class is responsible for generating responses for the chatbot.
    """

    def __init__(self):
        self.client = Groq(api_key=config.GROQ_API_KEY)
        self.model = "llama3-groq-70b-8192-tool-use-preview"
        self.searcher = PostgresSearcher(Product)

    def search_products(self, search_query: str):
        """
        This function is used to search products based on the search_query.
        """
        response: list[Product] = self.searcher.search_and_embed(search_query)
        if not response:
            return "No products found for the given search query."
        response = "\n".join([i.content for i in response])

        return (
            "Retrieved the following products based on your search query:\n"
            f"{response}"
        )

    def search_tool_definition(self):
        """
        This function is used to get the definition of the search tool.
        """
        return {
            "type": "function",
            "function": {
                "name": "search_products",
                "description": "This function is used to search products based on the search_query.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "search_query": {
                            "type": "string",
                            "description": (
                                "The search query to search the products.\n"
                                "eg: 'shoes for kids with size 5' or "
                                "summer wear for kids"
                            ),
                        },
                    },
                    "required": ["search_query"],
                },
            },
        }

    def generate_response(self, user_query):
        """
        This function is used to generate response for the user query.
        """
        messages = [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": user_query},
        ]
        while True:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tool_choice="auto",
                tools=[self.search_tool_definition()],
            )

            response_message = response.choices[0].message

            if response_message.tool_calls:
                tool_calls = response_message.tool_calls
                messages.append(
                    {
                        "role": "assistant",
                        "tool_calls": [
                            tool_call.model_dump() for tool_call in tool_calls
                        ],
                    }
                )
                tools_names = [tool_call.function.name for tool_call in tool_calls]
                logger.info(f"Tools used: {tools_names}")
                tool_call = tool_calls[0]
                try:
                    logger.info(f"Calling tool: {tool_call.function.name}")
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)
                    logger.info(f"Tool arguments: {tool_args}")
                    tool_result = self.search_products(**tool_args)
                except Exception as e: # pylint: disable=broad-except
                    tool_result = str(e)

                logger.info(f"Tool result: {tool_result}")
                messages.append(
                    {
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": tool_name,
                        "content": tool_result,
                    }
                )
            else:
                break

        return response_message.content
