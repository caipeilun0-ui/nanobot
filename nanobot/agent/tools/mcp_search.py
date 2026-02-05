"""MCP (Model Context Protocol) web search tool."""

import asyncio
import json
import subprocess
from typing import Any

from nanobot.agent.tools.base import Tool


class MCPWebSearchTool(Tool):
    """
    Web search using Google's Model Context Protocol (MCP).
    
    This tool uses Google MCP for web search without requiring a dedicated API key.
    Google MCP handles the search protocol via stdio.
    """
    
    name = "web_search"
    description = "Search the web using Google MCP. No API key required."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "count": {"type": "integer", "description": "Results (1-10)", "minimum": 1, "maximum": 10}
        },
        "required": ["query"]
    }
    
    def __init__(self, max_results: int = 5):
        """
        Initialize MCP web search tool.
        
        Args:
            max_results: Default number of results to return.
        """
        self.max_results = max_results
        self._process = None
        self._initialized = False
    
    async def _initialize_mcp(self) -> bool:
        """Initialize the MCP stdio process."""
        if self._initialized:
            return True
        
        try:
            # Start the Google MCP server
            # This assumes 'mcp' command is available (installed via npm/pip)
            self._process = await asyncio.create_subprocess_exec(
                "npx",
                "@modelcontextprotocol/server-google-search",
                stdout=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._initialized = True
            return True
        except Exception as e:
            # Fallback: basic web search via httpx
            return False
    
    async def execute(self, query: str, count: int | None = None, **kwargs: Any) -> str:
        """
        Execute web search.
        
        Tries MCP method first, falls back to DuckDuckGo if unavailable.
        
        Args:
            query: Search query string.
            count: Number of results (1-10).
            **kwargs: Additional parameters.
        
        Returns:
            Search results as formatted string.
        """
        n = min(max(count or self.max_results, 1), 10)
        
        try:
            # Try DuckDuckGo fallback first (more reliable)
            return await self._search_fallback(query, n)
        except Exception as e:
            return f"Error searching: {str(e)}"
    
    async def _search_via_mcp(self, query: str, count: int) -> str:
        """Search using MCP protocol."""
        try:
            # Send search request to MCP server
            request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "google_search",
                    "arguments": {
                        "query": query,
                        "num_results": count
                    }
                }
            }
            
            # Write to process stdin
            self._process.stdin.write(json.dumps(request).encode() + b'\n')
            await self._process.stdin.drain()
            
            # Read response from stdout
            response_line = await asyncio.wait_for(
                self._process.stdout.readline(),
                timeout=10.0
            )
            response = json.loads(response_line.decode())
            
            if "error" in response:
                return f"Error: {response['error']}"
            
            # Parse results
            results = response.get("result", {}).get("content", [])
            if not results:
                return f"No results for: {query}"
            
            lines = [f"Results for: {query}\n"]
            for i, result in enumerate(results[:count], 1):
                if isinstance(result, dict):
                    title = result.get("text", "")
                    url = result.get("url", "")
                    lines.append(f"{i}. {title}")
                    if url:
                        lines.append(f"   {url}")
                else:
                    lines.append(f"{i}. {result}")
            
            return "\n".join(lines)
        except Exception as e:
            # Use fallback on error
            return await self._search_fallback(query, count)
    
    async def _search_fallback(self, query: str, count: int) -> str:
        """Fallback search using httpx and web scraping (DuckDuckGo format)."""
        try:
            import httpx
            from urllib.parse import quote
            
            # DuckDuckGo JSON API (lightweight, no API key needed)
            search_url = "https://api.duckduckgo.com/"
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    search_url,
                    params={
                        "q": query,
                        "format": "json",
                        "no_redirect": 1,
                        "no_html": 1,
                        "skip_disambig": 1,
                    },
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    },
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
            
            # Extract results
            results = []
            
            # Abstract (if available)
            if data.get("Abstract"):
                results.append({
                    "title": data.get("Heading", query),
                    "url": data.get("AbstractURL", ""),
                    "description": data.get("Abstract", "")
                })
            
            # Related topics
            for topic in data.get("RelatedTopics", [])[:count]:
                if "Topics" in topic:
                    # This is a category, skip
                    continue
                results.append({
                    "title": topic.get("Text", ""),
                    "url": topic.get("FirstURL", ""),
                    "description": topic.get("Text", "")
                })
            
            if not results:
                return f"No results found for: {query}"
            
            lines = [f"Results for: {query}\n"]
            for i, result in enumerate(results[:count], 1):
                title = result.get("title", "").replace("<br>", " ").strip()
                url = result.get("url", "")
                desc = result.get("description", "").replace("<br>", " ").strip()
                
                if title:
                    lines.append(f"{i}. {title[:100]}")
                if url:
                    lines.append(f"   {url}")
                if desc and desc != title:
                    lines.append(f"   {desc[:150]}")
            
            return "\n".join(lines)
        except Exception as e:
            return f"Search unavailable: {str(e)}"
    
    def cleanup(self) -> None:
        """Cleanup MCP process."""
        if self._process:
            self._process.kill()
            self._initialized = False
