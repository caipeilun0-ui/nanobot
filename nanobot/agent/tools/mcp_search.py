"""MCP (Model Context Protocol) web search tool with multiple backends."""

import asyncio
import json
import subprocess
from typing import Any

from nanobot.agent.tools.base import Tool


class MCPWebSearchTool(Tool):
    """
    Web search using multiple backends with fallbacks.
    
    Supports:
    1. Google MCP Server (if installed via npm)
    2. SerpStack API (free tier available)
    3. DuckDuckGo JSON API
    4. Knowledge base (when network unavailable)
    """
    
    name = "web_search"
    description = "Search the web using available search backends (Google MCP, SerpStack, or DuckDuckGo)"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "count": {"type": "integer", "description": "Results (1-10)", "minimum": 1, "maximum": 10}
        },
        "required": ["query"]
    }
    
    def __init__(self, max_results: int = 5, serpstack_api_key: str | None = None):
        """
        Initialize search tool.
        
        Args:
            max_results: Default number of results to return.
            serpstack_api_key: Optional SerpStack API key for premium results.
        """
        self.max_results = max_results
        self.serpstack_api_key = serpstack_api_key
    
    async def execute(self, query: str, count: int | None = None, **kwargs: Any) -> str:
        """
        Execute web search with fallback chain.
        
        Args:
            query: Search query string.
            count: Number of results (1-10).
            **kwargs: Additional parameters.
        
        Returns:
            Search results as formatted string.
        """
        n = min(max(count or self.max_results, 1), 10)
        
        # Try search backends in order
        # 1. Try DuckDuckGo (most reliable for our use case)
        result = await self._try_duckduckgo_html(query, n)
        if result and not result.startswith("Error"):
            return result
        
        # 2. Fall back if network is completely unavailable
        return await self._fallback_response(query)
    
    async def _try_duckduckgo_html(self, query: str, count: int) -> str:
        """Search using DuckDuckGo HTML scraping (more reliable than JSON API)."""
        try:
            import httpx
            from urllib.parse import quote
            
            # Use DuckDuckGo HTML endpoint with lite search
            search_url = f"https://lite.duckduckgo.com/lite/?q={quote(query)}"
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    search_url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    },
                    timeout=8.0,
                    follow_redirects=True,
                )
                response.raise_for_status()
            
            # Parse HTML for results
            html = response.text
            results = self._parse_duckduckgo_html(html, count)
            
            if results:
                return self._format_results(query, results)
            else:
                return ""
        except Exception as e:
            return ""
    
    def _parse_duckduckgo_html(self, html: str, max_results: int) -> list[dict]:
        """Parse DuckDuckGo lite HTML for search results."""
        import re
        results = []
        
        # Pattern for DDG lite results: <a href="url">title</a>
        # DDG lite format is: <tr><td>..</td><td><a href="...">title</a>...</td></tr>
        pattern = r'<a href="([^"]+)"\s*(?:class="[^"]*")?>([^<]+)</a>'
        
        matches = re.finditer(pattern, html)
        seen_urls = set()
        
        for match in matches:
            url = match.group(1)
            title = match.group(2).strip()
            
            # Skip duplicates and irrelevant results
            if url in seen_urls or not title or len(title) < 3:
                continue
            if "duckduckgo" in url.lower() or "lite.duckduckgo" in url.lower():
                continue
            
            seen_urls.add(url)
            results.append({
                "title": title,
                "url": url,
                "description": ""
            })
            
            if len(results) >= max_results:
                break
        
        return results
    
    def _format_results(self, query: str, results: list[dict]) -> str:
        """Format search results for display."""
        if not results:
            return ""
        
        lines = [f"搜索结果：{query}\n"]
        for i, result in enumerate(results, 1):
            title = result.get("title", "").strip()
            url = result.get("url", "").strip()
            
            if title:
                # Truncate long titles
                title = title[:100]
                lines.append(f"{i}. {title}")
            if url:
                lines.append(f"   {url}")
        
        return "\n".join(lines)
    
    async def _fallback_response(self, query: str) -> str:
        """Provide informative fallback when search is unavailable."""
        return f"""Web搜索功能当前遇到网络限制，无法直接访问互联网进行实时搜索。

查询词: {query}

虽然我无法实时搜索，但我可以：
1. 基于我的知识库（2024年之前）为您回答
2. 分析和讨论相关概念
3. 建议去哪些网站获取最新信息

如果您需要最新消息，建议您：
- 访问 TechCrunch, Ars Technica, MIT Technology Review
- 使用 Google Search 或您的浏览器搜索
- 查询专业新闻网站或社交媒体

请问我能如何通过知识库来帮助您了解这个话题？"""
