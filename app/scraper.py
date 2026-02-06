"""
Web scraper wrapper for the Go web-parser binary
"""

import json
import subprocess
import asyncio
from typing import List, Dict, Any, Optional, Callable, AsyncIterator
from pathlib import Path


class ScrapingError(Exception):
    """Exception raised when scraping fails"""
    pass


class WebParser:
    """Wrapper for the web-parser Go binary"""
    
    def __init__(self, binary_path: str = "./web-parser/web-parser", timeout: int = 300):
        """
        Initialize WebParser
        
        Args:
            binary_path: Path to the web-parser binary
            timeout: Timeout in seconds (default 5 minutes)
        """
        self.binary_path = Path(binary_path)
        self.timeout = timeout
        
        if not self.binary_path.exists():
            raise FileNotFoundError(f"web-parser binary not found at {binary_path}")
    
    def scrape_page(self, url: str) -> Dict[str, Any]:
        """
        Scrape a single page (no crawling)
        
        Args:
            url: URL to scrape
            
        Returns:
            Dict with keys: url, title, content
            
        Raises:
            TimeoutError: If scraping times out
            ScrapingError: If scraping fails
            ValueError: If output cannot be parsed
        """
        try:
            cmd = [
                str(self.binary_path),
                "-url", url,
                "-format", "json",
                "-no-progress"
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False  # We'll handle errors ourselves
            )
            
            if result.returncode != 0:
                raise ScrapingError(f"web-parser failed with code {result.returncode}: {result.stderr}")
            
            # Parse JSON output
            # The output format is: {"pages": [...], "total_pages": N, "timestamp": "..."}
            # followed by "Scraping completed!" message
            # We need to extract just the JSON part
            output = result.stdout.strip()
            
            # Find the JSON object (starts with { and ends with })
            # We need to find the matching closing brace
            json_str = self._extract_json(output)
            
            if not json_str:
                raise ValueError(f"No valid JSON found in web-parser output")
            
            data = json.loads(json_str)
            
            # Extract first page from the pages array
            if "pages" in data and len(data["pages"]) > 0:
                return data["pages"][0]
            else:
                raise ValueError("No pages found in web-parser output")
            
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"Scraping {url} timed out after {self.timeout} seconds")
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse web-parser output: {e}")
    
    def _extract_json(self, text: str) -> Optional[str]:
        """
        Extract JSON object from text that may contain other messages.
        
        Args:
            text: Text containing JSON
            
        Returns:
            JSON string or None if not found
        """
        # Find first opening brace
        start = text.find('{')
        if start == -1:
            return None
        
        # Count braces to find matching closing brace
        brace_count = 0
        for i in range(start, len(text)):
            if text[i] == '{':
                brace_count += 1
            elif text[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    return text[start:i+1]
        
        return None
    
    def crawl(self, url: str, max_depth: int = 2) -> List[Dict[str, Any]]:
        """
        Crawl a website starting from URL
        
        Args:
            url: Starting URL
            max_depth: Maximum crawl depth (1-5)
            
        Returns:
            List of dicts with keys: url, title, content
            
        Raises:
            TimeoutError: If crawling times out
            ScrapingError: If crawling fails
            ValueError: If output cannot be parsed or max_depth is invalid
        """
        # Validate max_depth
        if not 1 <= max_depth <= 5:
            raise ValueError(f"max_depth must be between 1 and 5, got {max_depth}")
        
        try:
            cmd = [
                str(self.binary_path),
                "-url", url,
                "-format", "json",
                "-crawl",
                "-max-depth", str(max_depth),
                "-no-progress"
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False  # We'll handle errors ourselves
            )
            
            if result.returncode != 0:
                raise ScrapingError(f"web-parser failed with code {result.returncode}: {result.stderr}")
            
            # Parse JSON output
            # Extract JSON object from output
            output = result.stdout.strip()
            json_str = self._extract_json(output)
            
            if not json_str:
                raise ValueError(f"No valid JSON found in web-parser output")
            
            data = json.loads(json_str)
            
            # Extract pages array
            if "pages" in data:
                return data["pages"]
            else:
                raise ValueError("No pages array found in web-parser output")
            
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"Crawling {url} timed out after {self.timeout} seconds")
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse web-parser output: {e}")
    
    def scrape(self, url: str, crawl: bool = True, max_depth: int = 2) -> List[Dict[str, Any]]:
        """
        Scrape a URL with optional crawling
        
        Args:
            url: URL to scrape
            crawl: Whether to crawl related pages (default: True)
            max_depth: Maximum crawl depth if crawl=True (default: 2)
            
        Returns:
            List of page dicts with keys: url, title, content
            
        Raises:
            TimeoutError: If scraping times out
            ScrapingError: If scraping fails
            ValueError: If output cannot be parsed
        """
        if crawl:
            return self.crawl(url, max_depth)
        else:
            # Return single page as a list for consistent interface
            return [self.scrape_page(url)]
    
    async def async_scrape(
        self,
        url: str,
        crawl: bool = True,
        max_depth: int = 2,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Async scrape a URL and stream pages as they're found.
        
        Args:
            url: URL to scrape
            crawl: Whether to crawl related pages (default: True)
            max_depth: Maximum crawl depth if crawl=True (default: 2)
            progress_callback: Optional callback(page_count, current_url) called for each page
            
        Yields:
            Dict with keys: url, title, content for each page found
            
        Raises:
            TimeoutError: If scraping times out
            ScrapingError: If scraping fails
            ValueError: If output cannot be parsed
        """
        # Validate max_depth if crawling
        if crawl and not 1 <= max_depth <= 5:
            raise ValueError(f"max_depth must be between 1 and 5, got {max_depth}")
        
        # Build command
        cmd = [
            str(self.binary_path),
            "-url", url,
            "-format", "json",
            "-no-progress"
        ]
        
        if crawl:
            cmd.extend(["-crawl", "-max-depth", str(max_depth)])
        
        # Start subprocess
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Ensure stdout is available
            if proc.stdout is None:
                raise ScrapingError("Failed to capture stdout from web-parser")
            
            # Read output in chunks and try to parse JSON incrementally
            stdout_data = b""
            page_count = 0
            
            # Read stdout until process completes
            while True:
                try:
                    # Read with timeout
                    chunk = await asyncio.wait_for(
                        proc.stdout.read(8192),
                        timeout=self.timeout
                    )
                    
                    if not chunk:
                        # EOF reached
                        break
                    
                    stdout_data += chunk
                    
                    # Try to parse JSON to see if we have complete output
                    try:
                        output_str = stdout_data.decode('utf-8')
                        json_str = self._extract_json(output_str)
                        
                        if json_str:
                            data = json.loads(json_str)
                            pages = data.get("pages", [])
                            
                            # Yield any new pages we haven't seen yet
                            if len(pages) > page_count:
                                for page in pages[page_count:]:
                                    page_count += 1
                                    
                                    # Call progress callback if provided
                                    if progress_callback:
                                        progress_callback(page_count, page.get("url", ""))
                                    
                                    yield page
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        # Not enough data yet or invalid JSON, continue reading
                        continue
                        
                except asyncio.TimeoutError:
                    # Kill process if timeout exceeded
                    proc.kill()
                    await proc.wait()
                    raise TimeoutError(f"Scraping {url} timed out after {self.timeout} seconds")
            
            # Wait for process to complete
            returncode = await proc.wait()
            
            if returncode != 0:
                stderr_data = b""
                if proc.stderr:
                    stderr_data = await proc.stderr.read()
                raise ScrapingError(
                    f"web-parser failed with code {returncode}: {stderr_data.decode('utf-8', errors='ignore')}"
                )
            
            # Final parse to ensure we got all pages
            if stdout_data:
                output_str = stdout_data.decode('utf-8')
                json_str = self._extract_json(output_str)
                
                if json_str:
                    data = json.loads(json_str)
                    pages = data.get("pages", [])
                    
                    # Yield any remaining pages
                    if len(pages) > page_count:
                        for page in pages[page_count:]:
                            page_count += 1
                            
                            if progress_callback:
                                progress_callback(page_count, page.get("url", ""))
                            
                            yield page
                    
                    # Ensure we got at least one page
                    if page_count == 0:
                        raise ValueError("No pages found in web-parser output")
                else:
                    raise ValueError("No valid JSON found in web-parser output")
                    
        except asyncio.CancelledError:
            # Handle task cancellation
            if proc and proc.returncode is None:
                proc.kill()
                await proc.wait()
            raise

