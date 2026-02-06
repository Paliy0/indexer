"""
Unit tests for app/scraper.py - WebParser with mocked subprocess
"""

import pytest
import json
import subprocess
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from app.scraper import WebParser, ScrapingError


@pytest.fixture
def mock_binary_path(tmp_path):
    """Create a temporary mock binary path"""
    binary = tmp_path / "web-parser"
    binary.touch()
    binary.chmod(0o755)
    return str(binary)


class TestWebParserInit:
    """Test WebParser initialization"""
    
    def test_init_with_valid_binary(self, mock_binary_path):
        """Test initialization with valid binary path"""
        parser = WebParser(binary_path=mock_binary_path)
        assert parser.binary_path == Path(mock_binary_path)
        assert parser.timeout == 300  # Default timeout
    
    def test_init_with_custom_timeout(self, mock_binary_path):
        """Test initialization with custom timeout"""
        parser = WebParser(binary_path=mock_binary_path, timeout=600)
        assert parser.timeout == 600
    
    def test_init_with_nonexistent_binary(self):
        """Test initialization with non-existent binary raises FileNotFoundError"""
        with pytest.raises(FileNotFoundError):
            WebParser(binary_path="/nonexistent/path/to/binary")


class TestExtractJson:
    """Test JSON extraction helper method"""
    
    def test_extract_json_simple(self, mock_binary_path):
        """Test extracting simple JSON object"""
        parser = WebParser(binary_path=mock_binary_path)
        text = '{"key": "value"}'
        result = parser._extract_json(text)
        assert result == '{"key": "value"}'
    
    def test_extract_json_with_prefix(self, mock_binary_path):
        """Test extracting JSON with prefix text"""
        parser = WebParser(binary_path=mock_binary_path)
        text = 'Some prefix text {"key": "value"} some suffix'
        result = parser._extract_json(text)
        assert result == '{"key": "value"}'
    
    def test_extract_json_nested(self, mock_binary_path):
        """Test extracting nested JSON object"""
        parser = WebParser(binary_path=mock_binary_path)
        text = 'Prefix {"outer": {"inner": "value"}} Suffix'
        result = parser._extract_json(text)
        assert result == '{"outer": {"inner": "value"}}'
    
    def test_extract_json_complex(self, mock_binary_path):
        """Test extracting complex JSON with arrays and nested objects"""
        parser = WebParser(binary_path=mock_binary_path)
        text = 'Starting... {"pages": [{"url": "test", "data": {"nested": true}}], "total": 1}\nCompleted!'
        result = parser._extract_json(text)
        assert result == '{"pages": [{"url": "test", "data": {"nested": true}}], "total": 1}'
    
    def test_extract_json_no_json(self, mock_binary_path):
        """Test extracting from text with no JSON returns None"""
        parser = WebParser(binary_path=mock_binary_path)
        text = 'No JSON here at all'
        result = parser._extract_json(text)
        assert result is None
    
    def test_extract_json_unclosed_braces(self, mock_binary_path):
        """Test extracting from text with unclosed braces returns None"""
        parser = WebParser(binary_path=mock_binary_path)
        text = '{"key": "value"'
        result = parser._extract_json(text)
        assert result is None


class TestScrapePage:
    """Test single page scraping"""
    
    @patch('subprocess.run')
    def test_scrape_page_success(self, mock_run, mock_binary_path):
        """Test successful page scraping"""
        # Mock successful response
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            "pages": [{
                "url": "https://example.com",
                "title": "Example Domain",
                "content": "This domain is for use in illustrative examples."
            }],
            "total_pages": 1,
            "timestamp": "2024-01-01T00:00:00Z"
        }) + "\nScraping completed!"
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        parser = WebParser(binary_path=mock_binary_path)
        result = parser.scrape_page("https://example.com")
        
        # Verify subprocess.run was called correctly
        mock_run.assert_called_once()
        args = mock_run.call_args
        assert args[0][0] == [
            mock_binary_path,
            "-url", "https://example.com",
            "-format", "json",
            "-no-progress"
        ]
        assert args[1]['timeout'] == 300
        
        # Verify result
        assert result['url'] == "https://example.com"
        assert result['title'] == "Example Domain"
        assert "illustrative examples" in result['content']
    
    @patch('subprocess.run')
    def test_scrape_page_timeout(self, mock_run, mock_binary_path):
        """Test scraping timeout"""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=300)
        
        parser = WebParser(binary_path=mock_binary_path)
        
        with pytest.raises(TimeoutError) as exc_info:
            parser.scrape_page("https://example.com")
        
        assert "timed out" in str(exc_info.value)
        assert "300 seconds" in str(exc_info.value)
    
    @patch('subprocess.run')
    def test_scrape_page_command_failure(self, mock_run, mock_binary_path):
        """Test scraping when command returns non-zero exit code"""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Error: Invalid URL"
        mock_run.return_value = mock_result
        
        parser = WebParser(binary_path=mock_binary_path)
        
        with pytest.raises(ScrapingError) as exc_info:
            parser.scrape_page("https://example.com")
        
        assert "failed with code 1" in str(exc_info.value)
        assert "Invalid URL" in str(exc_info.value)
    
    @patch('subprocess.run')
    def test_scrape_page_invalid_json(self, mock_run, mock_binary_path):
        """Test scraping when output is not valid JSON"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Not valid JSON at all"
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        parser = WebParser(binary_path=mock_binary_path)
        
        with pytest.raises(ValueError) as exc_info:
            parser.scrape_page("https://example.com")
        
        assert "No valid JSON found" in str(exc_info.value)
    
    @patch('subprocess.run')
    def test_scrape_page_empty_pages_array(self, mock_run, mock_binary_path):
        """Test scraping when pages array is empty"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            "pages": [],
            "total_pages": 0
        })
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        parser = WebParser(binary_path=mock_binary_path)
        
        with pytest.raises(ValueError) as exc_info:
            parser.scrape_page("https://example.com")
        
        assert "No pages found" in str(exc_info.value)
    
    @patch('subprocess.run')
    def test_scrape_page_no_pages_key(self, mock_run, mock_binary_path):
        """Test scraping when JSON doesn't contain 'pages' key"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            "error": "Something went wrong"
        })
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        parser = WebParser(binary_path=mock_binary_path)
        
        with pytest.raises(ValueError) as exc_info:
            parser.scrape_page("https://example.com")
        
        assert "No pages found" in str(exc_info.value)


class TestCrawl:
    """Test website crawling"""
    
    @patch('subprocess.run')
    def test_crawl_success(self, mock_run, mock_binary_path):
        """Test successful crawling"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            "pages": [
                {
                    "url": "https://example.com",
                    "title": "Home",
                    "content": "Home page content"
                },
                {
                    "url": "https://example.com/about",
                    "title": "About",
                    "content": "About page content"
                },
                {
                    "url": "https://example.com/contact",
                    "title": "Contact",
                    "content": "Contact page content"
                }
            ],
            "total_pages": 3
        })
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        parser = WebParser(binary_path=mock_binary_path)
        results = parser.crawl("https://example.com", max_depth=2)
        
        # Verify subprocess.run was called correctly
        mock_run.assert_called_once()
        args = mock_run.call_args
        assert args[0][0] == [
            mock_binary_path,
            "-url", "https://example.com",
            "-format", "json",
            "-crawl",
            "-max-depth", "2",
            "-no-progress"
        ]
        
        # Verify results
        assert len(results) == 3
        assert results[0]['url'] == "https://example.com"
        assert results[1]['url'] == "https://example.com/about"
        assert results[2]['url'] == "https://example.com/contact"
    
    @patch('subprocess.run')
    def test_crawl_with_different_depths(self, mock_run, mock_binary_path):
        """Test crawling with different max_depth values"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"pages": [{"url": "test", "title": "Test", "content": "Test"}]})
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        parser = WebParser(binary_path=mock_binary_path)
        
        for depth in [1, 2, 3, 4, 5]:
            mock_run.reset_mock()
            parser.crawl("https://example.com", max_depth=depth)
            
            args = mock_run.call_args
            assert "-max-depth" in args[0][0]
            depth_index = args[0][0].index("-max-depth")
            assert args[0][0][depth_index + 1] == str(depth)
    
    def test_crawl_invalid_max_depth(self, mock_binary_path):
        """Test crawling with invalid max_depth raises ValueError"""
        parser = WebParser(binary_path=mock_binary_path)
        
        # Test max_depth too low
        with pytest.raises(ValueError) as exc_info:
            parser.crawl("https://example.com", max_depth=0)
        assert "must be between 1 and 5" in str(exc_info.value)
        
        # Test max_depth too high
        with pytest.raises(ValueError) as exc_info:
            parser.crawl("https://example.com", max_depth=10)
        assert "must be between 1 and 5" in str(exc_info.value)
    
    @patch('subprocess.run')
    def test_crawl_timeout(self, mock_run, mock_binary_path):
        """Test crawling timeout"""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=300)
        
        parser = WebParser(binary_path=mock_binary_path)
        
        with pytest.raises(TimeoutError) as exc_info:
            parser.crawl("https://example.com")
        
        assert "timed out" in str(exc_info.value)
    
    @patch('subprocess.run')
    def test_crawl_command_failure(self, mock_run, mock_binary_path):
        """Test crawling when command fails"""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Network error"
        mock_run.return_value = mock_result
        
        parser = WebParser(binary_path=mock_binary_path)
        
        with pytest.raises(ScrapingError) as exc_info:
            parser.crawl("https://example.com")
        
        assert "failed with code 1" in str(exc_info.value)
        assert "Network error" in str(exc_info.value)
    
    @patch('subprocess.run')
    def test_crawl_no_pages_array(self, mock_run, mock_binary_path):
        """Test crawling when response doesn't contain pages array"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"total_pages": 0})
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        parser = WebParser(binary_path=mock_binary_path)
        
        with pytest.raises(ValueError) as exc_info:
            parser.crawl("https://example.com")
        
        assert "No pages array found" in str(exc_info.value)


class TestScrapeMethod:
    """Test the unified scrape() method"""
    
    @patch('subprocess.run')
    def test_scrape_with_crawl_enabled(self, mock_run, mock_binary_path):
        """Test scrape() with crawl=True"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            "pages": [
                {"url": "https://example.com", "title": "Home", "content": "Content 1"},
                {"url": "https://example.com/page2", "title": "Page 2", "content": "Content 2"}
            ]
        })
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        parser = WebParser(binary_path=mock_binary_path)
        results = parser.scrape("https://example.com", crawl=True, max_depth=2)
        
        # Should call crawl, which uses -crawl flag
        args = mock_run.call_args
        assert "-crawl" in args[0][0]
        assert len(results) == 2
    
    @patch('subprocess.run')
    def test_scrape_with_crawl_disabled(self, mock_run, mock_binary_path):
        """Test scrape() with crawl=False"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            "pages": [
                {"url": "https://example.com", "title": "Home", "content": "Content"}
            ]
        })
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        parser = WebParser(binary_path=mock_binary_path)
        results = parser.scrape("https://example.com", crawl=False)
        
        # Should call scrape_page, which doesn't use -crawl flag
        args = mock_run.call_args
        assert "-crawl" not in args[0][0]
        assert len(results) == 1
        assert results[0]['url'] == "https://example.com"
    
    @patch('subprocess.run')
    def test_scrape_default_is_crawl(self, mock_run, mock_binary_path):
        """Test that scrape() defaults to crawl=True"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            "pages": [{"url": "test", "title": "Test", "content": "Content"}]
        })
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        parser = WebParser(binary_path=mock_binary_path)
        parser.scrape("https://example.com")
        
        # Should have -crawl flag
        args = mock_run.call_args
        assert "-crawl" in args[0][0]
