import json
import logging
import aiohttp
import trafilatura
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from redbot.core import commands

from gptmemory.schema import ToolCall, Function, Parameters
from gptmemory.constants import FARENHEIT_PATTERN
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
                }},
                required=["query"],
    )))

    async def run(self, arguments: dict) -> str:
        api_key = (await self.ctx.bot.get_shared_api_tokens("serper")).get("api_key")
        if not api_key:
            log.error("Tried to do a google search but serper api_key not found")
            return "An error occured while searching Google."
        
        query = arguments["query"]
        log.info(f"{query=}")
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
        
        content = "[Google Search result] "

        if answer_box := data.get("answerBox", {}):
            if "title" in answer_box and "answer" in answer_box:
                content += f"[Title: {answer_box['title']}] [Answer: {answer_box['answer']}] "
            if "source" in answer_box:
                content += f"[Source: {answer_box['source']}] "
            if "snippet" in answer_box:
                content += f"{answer_box['snippet']}"
        elif graph := data.get("knowledgeGraph", {}):
            if "title" in graph:
                content += f"[Title: {graph['title']}] "
            if "type" in graph:
                content += f"[Type: {graph['type']}] "
            if "description" in graph:
                content += f"[Description: {graph['description']}] "
            if "website" in graph:
                content += f"[Website: {graph['website']}]"
            for attribute, value in graph.get("attributes", {}).items():
                content += f"[{attribute}: {value}] "
        elif organic_results := data.get("organic", []):
            content += f"[Source: {organic_results[0]['link']}] {organic_results[0]['snippet']}"
        else:
            content += "Nothing relevant."

        content = content.strip()
        if len(content) > TOOL_CALL_LENGTH:
            content = content[:TOOL_CALL_LENGTH-3] + "..."
        return content


class ScrapeFunctionCall(FunctionBase):
    schema = ToolCall(
        Function(
            name="open_url",
            description="Opens a URL and returns its contents. Does not support non-text content types.",
            parameters=Parameters(
                properties={
                    "url": {
                        "type": "string",
                        "description": "The link to open",
                }},
                required=["query"],
    )))

    async def run(self, arguments: dict) -> str:
        link = arguments["url"]

        async with aiohttp.ClientSession(headers=SCRAPE_HEADERS) as session:
            async with session.get(link) as response:
                response.raise_for_status()
                content_type = response.headers.get('Content-Type', '').lower()
                if not 'text/html' in content_type:
                    return f"Contents of {link} is not text/html"
                
                content = trafilatura.extract(await response.text())

        if len(content) > TOOL_CALL_LENGTH:
            content = content[:TOOL_CALL_LENGTH-3] + "..."
        return f"[Contents of {link}:]\n{content}"
    

class WolframAlphaFunctionCall(FunctionBase):
    schema = ToolCall(
        Function(
            name="ask_wolframalpha",
            description="Asks Wolfram Alpha about math, exchange rates, or the weather, but not for unit conversions.",
            parameters=Parameters(
                    properties={
                        "query": {
                            "type": "string",
                            "description": "A math operation, currency conversion, or weather question"
                }},
                required=["query"],
    )))

    async def run(self, arguments: dict) -> str:
        api_key = (await self.ctx.bot.get_shared_api_tokens("wolframalpha")).get("appid")
        if not api_key:
            log.error("No appid set for wolframalpha")
            return "An error occured while asking Wolfram Alpha."

        url = "http://api.wolframalpha.com/v2/query?"
        query = arguments["query"]
        payload = {"input": query, "appid": api_key}
        headers = {"user-agent": "Red-cog/2.0.0"}

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url, params=payload) as response:
                    result = await response.text()
        except:
            log.exception("Asking Wolfram Alpha")
            return "An error occured while asking Wolfram Alpha."
        
        root = ET.fromstring(result)
        a = []
        for pt in root.findall(".//plaintext"):
            if pt.text:
                a.append(pt.text.capitalize())

        if len(a) < 1:
            return f"Wolfram Alpha is unable to answer the question \"{query}\". Try to answer with your own knowledge."
        else:
            content = "\n".join(a[:3]) # lines after the 3rd are often irrelevant in answers such as currency conversion
            if "Current geoip location" in content:
                return f"Wolfram Alpha is unable to answer the question \"{query}\". Try to answer with your own knowledge."
            
        if matches := FARENHEIT_PATTERN.findall(content):
            for match in list(set(matches)):
                content = content.replace(f"{int(match)} °f", f"{int(match)}°F/{(int(match)-32)*5/9:.1f}°C")

        if len(content) > TOOL_CALL_LENGTH:
            content = content[:TOOL_CALL_LENGTH-3] + "..."

        return f"[Wolfram Alpha] [Question: {query}] [Answer:] {content}"
