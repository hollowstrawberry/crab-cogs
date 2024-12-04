import json
import logging
import aiohttp
import trafilatura
from abc import ABC, abstractmethod
from redbot.core import commands

from gptmemory.schema import ToolCall, Function, Parameters
from gptmemory.constants import YOUTUBE_URL_PATTERN
from gptmemory.defaults import TOOL_CALL_LENGTH

log = logging.getLogger("red.crab-cogs.gptmemory")

SCRAPE_HEADERS = {
    "Cache-Control": "no-cache",
    "Referer": "https://www.google.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
}


class FunctionBase(ABC):
    schema: ToolCall = None

    def __init__(self, ctx: commands.Context):
        self.ctx = ctx

    @abstractmethod
    def run(self, arguments: dict) -> str:
        raise NotImplementedError


class SearchFunctionCall(FunctionBase):
    schema = ToolCall(
        Function(
            name="search_google",
            description="Googles a query for any unknown information or for updates on old information.",
            parameters=Parameters(
                properties={
                        "query": {
                            "type": "string",
                            "description": "The search query",
                        }
                },
                required=["query"]
    )))

    async def run(self, arguments: dict) -> str:
        api_key = (await self.ctx.bot.get_shared_api_tokens("serper")).get("api_key")
        if not api_key:
            log.error("Tried to do a google search but serper api_key not found")
            return "An error occured while searching Google."
        
        query = arguments["query"]
        payload = json.dumps({"q": query})
        headers = {'X-API-KEY': api_key, 'Content-Type': 'application/json'}
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.post("https://google.serper.dev/search", data=payload) as response:
                    response.raise_for_status()
                    data = await response.json()
        except:
            log.exception("Failed request to serper.io")
            return "An error occured while searching Google."
        
        answer_box = data.get("answerBox")
        if answer_box and "snippet" in answer_box:
            return f"Google Search result: {answer_box['snippet']}"

        organic_results = [result for result in data.get("organic", []) if not YOUTUBE_URL_PATTERN.search(result.get("link", ""))]
        if not organic_results:
            return "Google Search result: Nothing relevant"

        content = ""
        if graph := data.get("knowledgeGraph", {}):
            if "title" in graph:
                content += f"[Title: {graph['title']}] "
            if "type" in graph:
                content += f"[Type: {graph['type']}] "
            if "description" in graph:
                content += f"[Description: {graph['description']}] "
            for attribute, value in graph.get("attributes", {}).items():
                content += f"[{attribute}: {value}] "
        else:
            content = organic_results[0].get('snippet')

        content = content.strip()
        if len(content) > TOOL_CALL_LENGTH:
            content = content[:TOOL_CALL_LENGTH-3] + "..."
        return f"Google Search result: {content}"


class ScrapeFunctionCall:
    schema = ToolCall(
        function=Function(
            name="open_url",
            description="Opens a URL and returns its contents. Does not support non-text content types.",
            parameters=Parameters(
                properties={
                        "url": {
                            "type": "string",
                            "description": "The link to open",
                        }
                },
                required=["query"]
    )))

    async def run(self, arguments: dict) -> str:
        link = arguments["link"]

        async with aiohttp.ClientSession(headers=SCRAPE_HEADERS) as session:
            async with session.get(link) as response:
                response.raise_for_status()
                content_type = response.headers.get('Content-Type', '').lower()
                if not 'text/html' in content_type:
                    return f"Contents of {link} is not text/html"
                
                content = trafilatura.extract(await response.text())

        if len(content) > TOOL_CALL_LENGTH:
            content = content[:TOOL_CALL_LENGTH-3] + "..."
        return content
