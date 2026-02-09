"""
Site configuration model and utilities.

Defines the SiteConfig Pydantic model for per-site scraping configuration,
including CSS selectors, crawl depth, filtering rules, and other options.
"""

from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field, validator
import re


class SiteConfig(BaseModel):
    """
    Site-specific scraping configuration.
    
    This model defines all configurable parameters for how a site should be scraped,
    including content selection, crawling behavior, URL filtering, and request options.
    """
    
    # Content selection
    content_selector: str = Field(
        default="body",
        description="CSS selector for main content extraction (e.g., 'article', '.content', '#main')"
    )
    
    title_selector: str = Field(
        default="title",
        description="CSS selector for page title extraction"
    )
    
    exclude_selectors: List[str] = Field(
        default_factory=list,
        description="CSS selectors to exclude from content (e.g., 'nav', '.ads', '#comments')"
    )
    
    # Crawling options
    max_depth: int = Field(
        default=2,
        ge=1,
        le=5,
        description="Maximum crawl depth (1-5, where 1 is only the homepage)"
    )
    
    delay_ms: int = Field(
        default=200,
        ge=50,
        le=5000,
        description="Delay between requests in milliseconds (50-5000ms)"
    )
    
    respect_robots_txt: bool = Field(
        default=True,
        description="Respect robots.txt rules when crawling"
    )
    
    # URL filtering
    include_patterns: List[str] = Field(
        default_factory=lambda: [".*"],
        description="Regex patterns to include URLs (e.g., '^.*/blog/.*$')"
    )
    
    exclude_patterns: List[str] = Field(
        default_factory=list,
        description="Regex patterns to exclude URLs (e.g., '^.*\\.pdf$', '^.*/admin/.*$')"
    )
    
    # Auto-reindexing
    auto_reindex: bool = Field(
        default=False,
        description="Enable automatic re-indexing on a schedule"
    )
    
    reindex_interval_days: int = Field(
        default=7,
        ge=1,
        le=30,
        description="Days between automatic re-indexes when auto_reindex is enabled (1-30)"
    )
    
    # Advanced options
    custom_headers: Dict[str, str] = Field(
        default_factory=dict,
        description="Custom HTTP headers to send with requests"
    )
    
    user_agent: Optional[str] = Field(
        default=None,
        description="Custom user agent string (if None, uses web-parser default)"
    )
    
    @validator("include_patterns", "exclude_patterns")
    def validate_regex_patterns(cls, v):
        """Validate that regex patterns are valid."""
        for pattern in v:
            try:
                re.compile(pattern)
            except re.error as e:
                raise ValueError(f"Invalid regex pattern '{pattern}': {e}")
        return v
    
    @validator("custom_headers")
    def validate_headers(cls, v):
        """Validate custom headers."""
        validated = {}
        for key, value in v.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise ValueError(f"Header '{key}={value}' must be strings")
            validated[key.strip()] = value.strip()
        return validated
    
    def to_webparser_args(self) -> Dict[str, Any]:
        """
        Convert SiteConfig to web-parser command line arguments.
        
        Returns:
            Dictionary of web-parser compatible arguments
        """
        args = {
            "--max-depth": str(self.max_depth),
            "--delay": str(self.delay_ms),
            "--respect-robots": str(self.respect_robots_txt).lower(),
        }
        
        # Add selectors if they differ from defaults
        if self.content_selector != "body":
            args["--content-selector"] = self.content_selector
        
        if self.title_selector != "title":
            args["--title-selector"] = self.title_selector
        
        if self.exclude_selectors:
            args["--exclude-selector"] = ",".join(self.exclude_selectors)
        
        if self.include_patterns != [".*"]:
            args["--include-pattern"] = ",".join(self.include_patterns)
        
        if self.exclude_patterns:
            args["--exclude-pattern"] = ",".join(self.exclude_patterns)
        
        if self.custom_headers:
            # Convert headers to web-parser format: "Header: value"
            headers = [f"{k}: {v}" for k, v in self.custom_headers.items()]
            args["--header"] = ",".join(headers)
        
        if self.user_agent:
            args["--user-agent"] = self.user_agent
        
        return args
    
    @classmethod
    def default(cls) -> "SiteConfig":
        """Get default configuration."""
        return cls()


# Default configuration instance
DEFAULT_CONFIG = SiteConfig.default()