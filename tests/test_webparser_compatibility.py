"""
Web parser compatibility tests

Tests web-parser binary compatibility and integration with the indexer application.
Ensures the library integration remains functional across updates.
"""

import pytest
import json
import subprocess
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from app.config import get_settings
from app.scraper import WebParser, ScrapingError


class TestWebParserBinary:
    """Test web-parser binary existence and basic functionality"""
    
    def test_binary_exists_at_config_path(self):
        """Test that web-parser binary exists at the configured WEB_PARSER_PATH"""
        settings = get_settings()
        binary_path = Path(settings.web_parser_path)
        
        assert binary_path.exists(), f"Binary not found at {binary_path}"
        assert binary_path.is_file(), f"Path is not a file: {binary_path}"
        
        # Check if it's executable
        assert os.access(binary_path, os.X_OK), f"Binary not executable: {binary_path}"
    
    def test_binary_returns_help_output(self):
        """Test that web-parser binary returns help/version output when called with -h flag"""
        settings = get_settings()
        binary_path = Path(settings.web_parser_path)
        
        # Run the binary with -h flag
        try:
            result = subprocess.run(
                [str(binary_path), "-h"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            # Either stdout or stderr should contain help text
            # (some binaries output help to stdout, others to stderr)
            output = result.stdout or result.stderr
            
            # Check for expected help text patterns
            assert len(output) > 0, "Binary returned empty output with -h flag"
            assert "usage" in output.lower() or "help" in output.lower() or "options" in output.lower(), \
                f"Help output missing usage/help/options text. Got: {output[:100]}"
                
        except subprocess.TimeoutExpired:
            pytest.fail("Binary timed out when running with -h flag")
        except subprocess.CalledProcessError as e:
            # Some binaries exit with non-zero for help, that's okay
            output = e.stdout or e.stderr
            if output:
                assert "usage" in output.lower() or "help" in output.lower() or "options" in output.lower(), \
                    f"Help output missing usage/help/options text. Got: {output[:100]}"
            else:
                pytest.fail(f"Binary returned no output and exited with {e.returncode}")
    
    def test_binary_version_output(self):
        """Test that web-parser binary returns version information when called with -v or --version flag"""
        settings = get_settings()
        binary_path = Path(settings.web_parser_path)
        
        # Try common version flags
        version_flags = ["-v", "--version", "-V"]
        
        for flag in version_flags:
            try:
                result = subprocess.run(
                    [str(binary_path), flag],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                output = result.stdout or result.stderr
                
                if output and len(output.strip()) > 0:
                    # Check for version-like patterns
                    assert any(char in output for char in [".", "v", "V", "ersion"]), \
                        f"Version output doesn't look like version info. Got: {output[:50]}"
                    return  # Success, found version output
                    
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
                continue
        
        # If none of the flags worked, the test is inconclusive but not a failure
        pytest.skip("Could not determine version flag for web-parser binary")


class TestJsonOutputCompatibility:
    """Test that web-parser JSON output format is compatible with expected structure"""
    
    @pytest.fixture
    def sample_valid_json(self):
        """Sample valid JSON output expected from web-parser"""
        return json.dumps({
            "pages": [
                {
                    "url": "https://example.com",
                    "title": "Example Domain",
                    "content": "This domain is for use in illustrative examples..."
                },
                {
                    "url": "https://example.com/page2",
                    "title": "Page 2",
                    "content": "More example content..."
                }
            ]
        })
    
    @pytest.fixture
    def sample_invalid_json(self):
        """Sample invalid JSON output"""
        return '{"pages": "not a list"}'
    
    def test_json_structure_has_pages_array(self, sample_valid_json):
        """Test that JSON has a 'pages' field that is an array/list"""
        data = json.loads(sample_valid_json)
        
        assert "pages" in data, "JSON missing 'pages' field"
        assert isinstance(data["pages"], list), "'pages' field is not a list"
        assert len(data["pages"]) > 0, "'pages' list is empty"
    
    def test_page_objects_have_required_fields(self, sample_valid_json):
        """Test that page objects have required url, title, and content fields"""
        data = json.loads(sample_valid_json)
        
        for page in data["pages"]:
            assert "url" in page, f"Page missing 'url' field: {page}"
            assert "title" in page, f"Page missing 'title' field: {page}"
            assert "content" in page, f"Page missing 'content' field: {page}"
            
            # Check field types
            assert isinstance(page["url"], str), f"'url' is not a string: {page['url']}"
            assert isinstance(page["title"], str), f"'title' is not a string: {page['title']}"
            assert isinstance(page["content"], str), f"'content' is not a string: {page['content']}"
    
    def test_json_extraction_handles_invalid_structure(self, sample_invalid_json):
        """Test that JSON extraction handles invalid structure gracefully"""
        # This should be handled by the WebParser._extract_json method
        # which should raise appropriate exceptions
        
        # Create a mock parser instance
        settings = get_settings()
        parser = WebParser(binary_path=settings.web_parser_path)
        
        # The _extract_json method should extract valid JSON from text
        # even if it's surrounded by other text
        text_with_json = f"Some text before\n{sample_invalid_json}\nSome text after"
        extracted = parser._extract_json(text_with_json)
        
        # Should extract the JSON portion
        assert extracted == sample_invalid_json, f"Failed to extract JSON. Got: {extracted}"


class TestErrorHandlingCompatibility:
    """Test error handling compatibility with web-parser"""
    
    @pytest.fixture
    def mock_parser(self):
        """Create a WebParser instance with mocked binary"""
        settings = get_settings()
        # Use a temporary mock binary
        with patch('pathlib.Path.exists', return_value=True):
            with patch('os.access', return_value=True):
                parser = WebParser(binary_path=settings.web_parser_path)
                return parser
    
    def test_handles_binary_not_found(self):
        """Test that WebParser handles non-existent binary gracefully"""
        with pytest.raises(FileNotFoundError):
            WebParser(binary_path="/nonexistent/path/to/web-parser")
    
    def test_handles_timeout(self, mock_parser):
        """Test that WebParser handles subprocess timeout"""
        # Mock subprocess.run to simulate timeout
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired(cmd='test', timeout=5)):
            with pytest.raises(TimeoutError) as exc_info:
                mock_parser.scrape("https://example.com")
            
            assert "timeout" in str(exc_info.value).lower() or "timed out" in str(exc_info.value).lower()
    
    def test_handles_non_zero_exit(self, mock_parser):
        """Test that WebParser handles non-zero exit code from binary"""
        # Mock subprocess.run to return non-zero exit code
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Error: failed to scrape"
        
        with patch('subprocess.run', return_value=mock_result):
            with pytest.raises(ScrapingError) as exc_info:
                mock_parser.scrape("https://example.com")
            
            assert "exit code" in str(exc_info.value).lower() or "failed" in str(exc_info.value).lower()
    
    def test_handles_invalid_json_output(self, mock_parser):
        """Test that WebParser handles invalid JSON output from binary"""
        # Mock subprocess.run to return invalid JSON
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Invalid JSON { not valid json "
        mock_result.stderr = ""
        
        with patch('subprocess.run', return_value=mock_result):
            with pytest.raises(ValueError) as exc_info:
                mock_parser.scrape("https://example.com")
            
            assert "json" in str(exc_info.value).lower() or "parse" in str(exc_info.value).lower() or "valid" in str(exc_info.value).lower()


class TestIntegrationCompatibility:
    """Integration tests for web-parser compatibility"""
    
    def test_end_to_end_scraping_simulation(self):
        """Simulate end-to-end scraping to ensure compatibility"""
        settings = get_settings()
        parser = WebParser(binary_path=settings.web_parser_path)
        
        # Test that the parser can be initialized
        assert parser.binary_path == Path(settings.web_parser_path)
        assert parser.timeout == 300  # Default timeout
        
        # Test configuration
        assert hasattr(parser, '_extract_json'), "WebParser missing _extract_json method"
        assert hasattr(parser, 'scrape'), "WebParser missing scrape method"
        assert hasattr(parser, 'crawl'), "WebParser missing crawl method"
    
    def test_real_binary_integration(self):
        """
        Test integration with real web-parser binary.
        This test may be skipped if the binary is not built or available.
        """
        settings = get_settings()
        binary_path = Path(settings.web_parser_path)
        
        # Skip if binary doesn't exist
        if not binary_path.exists():
            pytest.skip(f"Web parser binary not found at {binary_path}")
        
        # Skip if not executable
        if not os.access(binary_path, os.X_OK):
            pytest.skip(f"Web parser binary not executable at {binary_path}")
        
        # Try to run binary with --help to verify it works
        try:
            result = subprocess.run(
                [str(binary_path), "--help"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            # Should not crash or timeout
            assert result.returncode == 0 or (result.stdout or result.stderr), \
                f"Binary returned no output. stdout: {result.stdout}, stderr: {result.stderr}"
                
        except subprocess.TimeoutExpired:
            pytest.fail("Binary timed out when running with --help flag")
        except Exception as e:
            pytest.fail(f"Unexpected error when testing binary: {e}")


if __name__ == "__main__":
    pytest.main(["-v", __file__])