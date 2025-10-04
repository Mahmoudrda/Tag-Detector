# Tag Detector

A comprehensive Python tool for detecting marketing and analytics tags on websites, including Google Tag Manager, Tealium, Meta Pixel, TikTok Pixel, and more.

## Overview

Tag Detector analyzes websites to detect the presence of various marketing and analytics tags. It performs both static HTML analysis and dynamic JavaScript execution to catch tags that load progressively or after user interaction.

## Features

- **Multiple Tag Detection**: Supports 8 major tag platforms
  - Google Tag Manager (GTM)
  - Tealium
  - Google Analytics (gtag & Universal Analytics)
  - Meta Pixel (Facebook)
  - TikTok Pixel
  - LinkedIn Insight Tag
  - Snap Pixel

- **Dual Analysis Modes**
  - Static HTML parsing for fast detection
  - JavaScript execution for dynamic tags (optional)

- **Advanced Detection**
  - Progressive loading detection for Single Page Applications (SPAs)
  - Confidence scoring system
  - Retry logic with exponential backoff
  - Consent manager and lazy loading detection

- **Performance Optimized**
  - Concurrent URL processing
  - Adaptive timeout strategies
  - Domain performance tracking

## Requirements

### Required Dependencies
```bash
pip install requests beautifulsoup4
```

### Optional (Recommended for 30-40% Better Accuracy)
```bash
pip install playwright
playwright install chromium
```

Without Playwright, the tool runs in static-only mode, which is faster but may miss dynamically loaded tags.

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/tag-Detector.git
cd tag-Detector
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. (Optional) Install Playwright for JavaScript execution:
```bash
pip install playwright
playwright install chromium
```

## Usage

### Basic Usage

1. Prepare a CSV file with URLs in a column named `URL`:
```csv
URL
https://example.com
https://another-site.com
```

2. Edit the configuration in `main()`:
```python
csv_file_path = 'your-urls.csv'
url_column_name = 'URL'
output_file = 'tag_detection_results.csv'
```

3. Run the script:
```bash
python tag_Detector.py
```

### Configuration Options

```python
Detector = tagDetector(
    use_javascript=True,    # Enable/disable JavaScript execution
    timeout=20,             # Timeout in seconds
    max_workers=2,          # Concurrent workers
    retry_config=RetryConfig(max_retries=2, backoff_factor=1)
)
```

### Output

The tool generates a CSV file with detailed results for each URL:
- Detection status for each tag type
- Confidence scores
- Tag identifiers (IDs, container IDs, etc.)
- Detection methods used
- Verification checks performed
- Warnings and implementation details

## How It Works

1. **Static Analysis**: Parses HTML and scripts for tag patterns
2. **Dynamic Analysis** (optional): Executes JavaScript and monitors network requests
3. **Progressive Loading**: Detects SPAs and waits for delayed tag loading
4. **Result Merging**: Combines static and dynamic results with calibrated confidence scores
5. **Export**: Saves comprehensive results to CSV

## Detection Methods

Each tag type is detected using multiple methods:
- Container/ID pattern matching
- Script URL detection
- Function call detection
- Network request monitoring
- DOM inspection
- Noscript fallback detection

## Performance

- **Static mode**: ~1-2 seconds per URL
- **JavaScript mode**: ~8-15 seconds per URL (varies by site complexity)
- Concurrent processing with configurable workers
- Adaptive timeouts based on domain performance history

## Extending

Add custom tag detectors by creating a new plugin class:

```python
class CustomTagDetectorPlugin(TagDetectorPlugin):
    @property
    def name(self) -> str:
        return "Custom Tag"
    
    @property
    def version(self) -> str:
        return "1.0.0"
    
    def detect_static(self, html_content, scripts, patterns):
        # Your detection logic
        pass
    
    def detect_dynamic(self, network_requests, console_logs, dom_content, patterns):
        # Your dynamic detection logic
        pass
```

Register your plugin:
```python
Detector.register_plugin('custom_tag', CustomTagDetectorPlugin())
```

## Limitations

- Requires stable internet connection
- Some tags behind authentication walls may not be detected
- Heavy JavaScript sites may require longer timeouts
- Rate limiting may affect large batch processing


## Troubleshooting

**Playwright not installed**: The tool will run in static-only mode. Install Playwright for full functionality.

**Timeout errors**: Increase the `timeout` parameter or check your internet connection.

**Missing CSV column**: Ensure your CSV has the correct column name specified in `url_column_name`.

**Memory issues**: Reduce `max_workers` for large URL batches.
