#!/usr/bin/env python3
"""Test script to debug URL detection"""

from utils import URLValidator
import re

# Test URLs from the screenshot
test_urls = [
    "https://www.instagram.com/reel/DGLPweS1Nau6r?igsh=MTR1ZWNjNmE5ZG1oNA==",
    "https://www.instagram.com/reel/DGLPweS1Nau6r",
    "https://instagram.com/reel/DGLPweS1Nau6r",
]

print("Testing URL detection:")
print("=" * 50)

for test_url in test_urls:
    print(f"\nTesting URL: {test_url}")
    
    # Test individual methods
    print(f"is_instagram_url: {URLValidator.is_instagram_url(test_url)}")
    print(f"is_valid_url: {URLValidator.is_valid_url(test_url)}")
    print(f"get_url_type: {URLValidator.get_url_type(test_url)}")
    print(f"normalize_url: {URLValidator.normalize_url(test_url)}")
    
    # Test regex patterns directly
    print("\nTesting against patterns:")
    for i, pattern in enumerate(URLValidator.INSTAGRAM_PATTERNS):
        match = re.match(pattern, test_url, re.IGNORECASE)
        print(f"Pattern {i+1}: {bool(match)} - {pattern}")
    
    print("-" * 30)

# Test extract_urls_from_text with sample text
test_text = "Check this out: https://www.instagram.com/reel/DGLPweS1Nau6r?igsh=MTR1ZWNjNmE5ZG1oNA=="

print(f"\n\nTesting extract_urls_from_text:")
print(f"Text: {test_text}")
extracted = URLValidator.extract_urls_from_text(test_text)
print(f"Extracted URLs: {extracted}")

# Test with general URL pattern
general_pattern = r'https?://[^\s]+'
general_matches = re.findall(general_pattern, test_text, re.IGNORECASE)
print(f"General pattern matches: {general_matches}")

for url in general_matches:
    clean_url = url.rstrip('.,!?;:)')
    print(f"Clean URL: {clean_url}")
    print(f"Is valid: {URLValidator.is_valid_url(clean_url)}")
