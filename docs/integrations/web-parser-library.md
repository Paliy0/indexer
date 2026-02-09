# Web-Parser Library Integration

## Overview

This indexer project uses [web-parser](https://github.com/Paliy0/web-parser), an open-source Go library for web scraping, as its core scraping engine. The web-parser library provides powerful web scraping capabilities including:

- **Content extraction**: Converts HTML to clean text and Markdown
- **Recursive crawling**: Follows links with configurable depth limits
- **Robust error handling**: Timeouts, retries, and graceful failure
- **JSON output**: Structured data for easy parsing

The indexer serves as a real-world showcase of how to integrate web-parser into a production application. Rather than embedding the library as a submodule, the indexer treats web-parser as an external dependency that can be updated independently.

## Installation & Usage

### Building the Binary

The web-parser binary must be built from the library source:

```bash
# Clone or update the web-parser library
git clone https://github.com/Paliy0/web-parser.git
cd web-parser

# Build the binary from the cmd/web-parser directory
go build -o web-parser ./cmd/web-parser

# Verify it works
./web-parser -h
```

### Configuration

The indexer expects the web-parser binary to be available at a specific path, configured via the `WEB_PARSER_PATH` environment variable:

```bash
# In .env file
WEB_PARSER_PATH=./web-parser/web-parser
```

Or specify an absolute path:

```bash
WEB_PARSER_PATH=/usr/local/bin/web-parser
```

### Integration Architecture

The indexer interacts with web-parser through a wrapper class (`app/scraper.py`):

1. **Subprocess Execution**: The `WebParser` class uses Python's `subprocess` module to execute the Go binary
2. **JSON Communication**: The binary outputs JSON that the Python wrapper parses
3. **Error Handling**: Timeouts, exit codes, and parsing errors are handled gracefully

Example usage from Python:

```python
from app.scraper import WebParser

# Initialize with binary path
parser = WebParser(binary_path="./web-parser/web-parser")

# Scrape a single page
page_data = parser.scrape_page("https://example.com")

# Scrape with crawling (up to 2 levels deep)
async for page in parser.async_scrape("https://example.com", max_depth=2):
    process_page(page)
```

## Binary Command-Line Interface

The web-parser binary supports various command-line options:

```bash
# Basic usage
./web-parser -url https://example.com

# Output format options
./web-parser -url https://example.com -format json      # JSON output
./web-parser -url https://example.com -format markdown  # Markdown output

# Crawling options
./web-parser -url https://example.com -max-depth 2      # Crawl up to 2 levels
./web-parser -url https://example.com -same-domain     # Only crawl same domain

# Performance options  
./web-parser -url https://example.com -delay 200        # 200ms delay between requests
./web-parser -url https://example.com -timeout 30       # 30 second timeout
./web-parser -url https://example.com -workers 4        # Use 4 concurrent workers

# Debug options
./web-parser -url https://example.com -no-progress      # Disable progress output
./web-parser -url https://example.com -verbose          # Enable verbose logging
```

## JSON Output Format

The web-parser JSON output has the following structure:

```json
{
  "pages": [
    {
      "url": "https://example.com",
      "title": "Example Domain",
      "content": "This domain is for use in illustrative examples...",
      "metadata": {
        "depth": 0,
        "status": 200,
        "timestamp": "2024-01-01T12:00:00Z",
        "content_type": "text/html"
      }
    }
  ],
  "total_pages": 1,
  "timestamp": "2024-01-01T12:00:00Z",
  "stats": {
    "successful": 1,
    "failed": 0,
    "total": 1
  }
}
```

## Troubleshooting

### Binary Not Found

**Error**: `FileNotFoundError: web-parser binary not found at ...`

**Solution**:
1. Verify the binary exists: `ls -la ./web-parser/web-parser`
2. Check file permissions: `chmod +x ./web-parser/web-parser`
3. Update WEB_PARSER_PATH in your .env file

### Permission Denied

**Error**: `PermissionError: [Errno 13] Permission denied`

**Solution**:
```bash
# Make the binary executable
chmod +x ./web-parser/web-parser

# Or run with sudo if in system directory
sudo chmod +x /usr/local/bin/web-parser
```

### JSON Parsing Errors

**Error**: `ValueError: Failed to parse web-parser output`

**Solution**:
1. Run the binary manually to see actual output: `./web-parser/web-parser -url https://example.com -format json -no-progress`
2. Check for Go compilation issues: `cd web-parser && go version && go build -o web-parser ./cmd/web-parser`
3. Verify Go installation: `go version`

### Timeout Errors

**Error**: `TimeoutError: Scraping ... timed out after ... seconds`

**Solution**:
1. Increase the timeout in app/scraper.py WebParser constructor
2. Use the binary's timeout flag: `-timeout 60`
3. Check network connectivity and website availability

### Version Mismatch

**Symptoms**: Unexpected output format or missing fields

**Solution**:
1. Check web-parser version: `./web-parser/web-parser -version`
2. Update to the latest version:
   ```bash
   cd web-parser
   git pull origin main
   go build -o web-parser ./cmd/web-parser
   ```
3. Review release notes at https://github.com/Paliy0/web-parser/releases

## Development Workflow

### Updating the Library

```bash
# Pull latest changes
cd web-parser
git pull origin main

# Rebuild binary
go build -o web-parser ./cmd/web-parser

# Test the binary
./web-parser -url https://example.com -format json -no-progress

# Run indexer tests to ensure compatibility
cd ..
pytest tests/test_webparser_compatibility.py
```

### Debugging Integration Issues

1. **Enable verbose logging** in app/scraper.py by adding `-verbose` flag to command
2. **Capture stderr** from subprocess to see Go errors
3. **Test binary directly** to isolate issues
4. **Check Go dependencies**: `cd web-parser && go mod tidy`

## Resources

- **Library Repository**: https://github.com/Paliy0/web-parser
- **Go Documentation**: https://golang.org/doc/
- **Issue Tracker**: https://github.com/Paliy0/web-parser/issues
- **Contributing Guide**: https://github.com/Paliy0/web-parser/blob/main/CONTRIBUTING.md
- **Indexer Project**: This repository serves as a reference implementation

## License Notes

The web-parser library is licensed under MIT. This indexer project includes web-parser as an external dependency but does not bundle the source code. Users must build the binary separately, ensuring compliance with both MIT license terms and any website terms of service when scraping.