import json
import logging
import aiohttp
import trafilatura
from abc import ABC, abstractmethod
from redbot.core import Config, commands

from gptmemory.schema import ToolCall, Function, Parameters
from gptmemory.constants import YOUTUBE_URL_PATTERN
from gptmemory.defaults import SEARCH_LENGTH

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
            )
        )
    )

    async def run(self, arguments: dict) -> str:
        api_key = (await self.ctx.bot.get_shared_api_tokens("serper")).get("api_key")
        if not api_key:
            log.error("Tried to do a google search but serper api_key not found")
            return "An error occured while searching Google."
        query = json.loads(arguments["query"])["description"]
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

        first_result = organic_results[0]
        link = first_result.get("link")
        text_content = ""
        try:
            log.info(f"Requesting {link} from Google query \"{self.query}\" in {self.guild}")
            async with aiohttp.ClientSession(headers=SCRAPE_HEADERS) as session:
                async with session.get(link) as response:
                    response.raise_for_status()
                    text_content = trafilatura.extract(await response.text())        
        except:
            log.warning(f"Failed scraping URL {link}", exc_info=True)
            graph = data.get("knowledgeGraph", {})
            if graph:
                if "title" in graph:
                    text_content += f"[Title: {graph['title']}] "
                if "type" in graph:
                    text_content += f"[Type: {graph['title']}] "
                if "description" in graph:
                    text_content += f"[Description: {graph['description']}] "
                for attribute, value in graph.get("attributes", {}).items():
                    text_content += f"[{attribute}: {value}] "
            else:
                text_content = first_result.get('snippet')

        text_content = text_content.strip()
        if len(text_content) > SEARCH_LENGTH:
            text_content = text_content[:SEARCH_LENGTH] + "..."
        return f"Google Search result: {text_content}"
