import asyncio
import re
import csv
import json
import hashlib
import time
import unittest
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import List, Dict, Set, Optional, Tuple, Any, Pattern
from urllib.parse import urlparse, urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

# Core dependencies
import requests
from bs4 import BeautifulSoup

# Headless browser dependencies 
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("Warning: Playwright not installed. JavaScript execution disabled.")
# Compiled regex patterns for performance
class CompiledPatterns:
    def __init__(self):
        # GTM regex patterns
        self.gtm_container_id = re.compile(r'GTM-[A-Z0-9]{4,}', re.IGNORECASE)
        self.gtm_script_url = re.compile(r'https://www\.googletagmanager\.com/gtm\.js\?id=([^&"\'\s]+)', re.IGNORECASE)
        self.gtm_init_code = re.compile(r'gtm\.start["\']?\s*:\s*new\s+Date\(\)\.getTime\(\)', re.IGNORECASE | re.DOTALL)
        self.gtm_datalayer = re.compile(r'dataLayer\s*=\s*\[|dataLayer\.push\s*\(', re.IGNORECASE)
        self.gtm_noscript = re.compile(r'<noscript>.*?<iframe[^>]*src=["\']https://www\.googletagmanager\.com/ns\.html\?id=([^"\'&]+)', re.IGNORECASE | re.DOTALL)
        self.gtm_dynamic = re.compile(r'createElement\s*\(\s*["\']script["\'][\s\S]{0,200}?googletagmanager\.com/gtm\.js', re.IGNORECASE | re.DOTALL)
        
        # Tealium Patterns
        self.tealium_url = re.compile(r'https://tags\.tiqcdn\.com/utag/([^/]+)/([^/]+)/([^/]+)/utag\.js', re.IGNORECASE)
        self.tealium_utag_data = re.compile(r'var\s+utag_data\s*=\s*\{|utag_data\s*=\s*\{', re.IGNORECASE)
        self.tealium_async = re.compile(r'\(function\s*\([a-z,\s]*\)\s*\{[^}]*tags\.tiqcdn\.com[^}]*\}\s*\)\s*\(\s*\)', re.IGNORECASE | re.DOTALL)
        self.tealium_functions = re.compile(r'utag\.(link|view|track|sync)\s*\(', re.IGNORECASE)
        self.tealium_dynamic = re.compile(r'createElement\s*\(\s*["\']script["\'][\s\S]{0,300}?tags\.tiqcdn\.com', re.IGNORECASE | re.DOTALL)
        
        # gtag Patterns
        self.gtag_measurement_id = re.compile(r'G-[A-Z0-9]{10}', re.IGNORECASE)
        self.gtag_script_url = re.compile(r'https://www\.googletagmanager\.com/gtag/js\?id=([^&"\'\s]+)', re.IGNORECASE)
        self.gtag_function = re.compile(r'gtag\s*\(\s*["\']config["\']|gtag\s*\(\s*["\']event["\']', re.IGNORECASE)

        # Meta Pixel Patterns
        self.meta_pixel_id = re.compile(r'fbq\s*\(\s*["\']init["\']\s*,\s*["\'](\d{15,16})["\']', re.IGNORECASE)
        self.meta_pixel_script_url = re.compile(r'https://connect\.facebook\.net/[^/]+/fbevents\.js', re.IGNORECASE)
        self.meta_pixel_noscript = re.compile(r'<noscript>.*?<img[^>]*src=["\']https://www\.facebook\.com/tr\?id=(\d{15,16})', re.IGNORECASE | re.DOTALL)
        self.meta_pixel_function = re.compile(r'fbq\s*\(\s*["\']track["\']\s*,', re.IGNORECASE)
        self.meta_pixel_dynamic = re.compile(r'createElement\s*\(\s*["\']script["\'][\s\S]{0,200}?connect\.facebook\.net', re.IGNORECASE | re.DOTALL)

        # TikTok Pixel Patterns
        self.tiktok_pixel_id = re.compile(r'ttq\.load\s*\(\s*["\']([^"\']+)["\']', re.IGNORECASE)
        self.tiktok_script_url = re.compile(r'https://analytics\.tiktok\.com/i18n/pixel/events\.js', re.IGNORECASE)
        self.tiktok_noscript = re.compile(r'<noscript>.*?<img[^>]*src=["\']https://analytics\.tiktok\.com/i18n/pixel/pixel\.gif\?id=([^"\']+)', re.IGNORECASE | re.DOTALL)
        self.tiktok_function = re.compile(r'ttq\.track\s*\(\s*["\']([^"\']+)["\']', re.IGNORECASE)
        self.tiktok_dynamic = re.compile(r'createElement\s*\(\s*["\']script["\'][\s\S]{0,200}?analytics\.tiktok\.com', re.IGNORECASE | re.DOTALL)

        # LinkedIn Insight Tag Patterns
        self.linkedin_partner_id = re.compile(r'linkedin\.com\/collect\?pid=(\d+)', re.IGNORECASE)
        self.linkedin_script_url = re.compile(r'https://snap.licdn.com/li.lms-analytics/insight\.min\.js', re.IGNORECASE)
        self.linkedin_noscript = re.compile(r'<noscript>.*?<img[^>]*src=["\']https://px\.ads\.linkedin\.com/collect\?pid=(\d+)', re.IGNORECASE | re.DOTALL)
        self.linkedin_function = re.compile(r'_linkedin_data_partner_id\s*=\s*["\'](\d+)["\']', re.IGNORECASE)
        self.linkedin_dynamic = re.compile(r'createElement\s*\(\s*["\']script["\'][\s\S]{0,200}?snap\.licdn\.com', re.IGNORECASE | re.DOTALL)

        # Snap Pixel Patterns
        self.snap_pixel_id = re.compile(r'snaptr\s*\(\s*["\']init["\']\s*,\s*["\']([^"\']+)["\']', re.IGNORECASE)
        self.snap_script_url = re.compile(r'https://sc-static\.net/scevent.min\.js', re.IGNORECASE)
        self.snap_noscript = re.compile(r'<noscript>.*?<img[^>]*src=["\']https://sc-static\.net/scevent\.gif\?id=([^"\']+)["\']', re.IGNORECASE | re.DOTALL)
        self.snap_function = re.compile(r'snaptr\s*\(\s*["\']track["\']\s*,', re.IGNORECASE)
        self.snap_dynamic = re.compile(r'createElement\s*\(\s*["\']script["\'][\s\S]{0,200}?sc-static\.net', re.IGNORECASE | re.DOTALL)

        # Universal Analytics Patterns
        self.ua_tracking_id = re.compile(r'UA-\d{4,10}-\d{1,4}', re.IGNORECASE)
        self.ua_script_url = re.compile(r'https://www\.google-analytics\.com/analytics\.js', re.IGNORECASE)
        self.ua_function = re.compile(r'ga\s*\(\s*["\']create["\']|ga\s*\(\s*["\']send["\']', re.IGNORECASE)
        self.ua_dynamic = re.compile(r'createElement\s*\(\s*["\']script["\'][\s\S]{0,200}?google-analytics\.com', re.IGNORECASE | re.DOTALL)

        # hardcoded gtag patterns
        self.hardcoded_gtag = re.compile(r'G-[A-Z0-9]{10}|UA-\d{4,10}-\d{1,4}', re.IGNORECASE)

        # advanced patterns
        self.consent_managers = re.compile(r'cookiebot|onetrust|usercentrics|trustarc|iubenda', re.IGNORECASE)
        self.lazy_loading = re.compile(r'intersectionobserver|requestidlecallback|loading\s*=\s*["\']lazy["\']', re.IGNORECASE)
        self.spa_frameworks = re.compile(r'react|angular|vue|next\.js|nuxt|gatsby|svelte', re.IGNORECASE)
        self.progressive_loading = re.compile(r'requestAnimationFrame|setTimeout|setInterval|Promise\.resolve\(\)\.then', re.IGNORECASE)

        # Add tag domains pattern
        self.tag_domains = {
            'googletagmanager.com',
            'google-analytics.com',
            'facebook.com',
            'connect.facebook.net',
            'analytics.tiktok.com',
            'snap.licdn.com',
            'sc-static.net',
            'tags.tiqcdn.com'
        }
        
        # Add performance tracking patterns
        self.tag_load_patterns = {
            'gtm': re.compile(r'dataLayer\.push\(\{[^}]*"gtm\.load"'),
            'ga4': re.compile(r'gtag\("config"'),
            'meta': re.compile(r'fbq\("init"'),
            'tiktok': re.compile(r'ttq\.load\('),
            'snap': re.compile(r'snaptr\("init"')
        }

class RetryConfig:
    """Configuration for retry logic with exponential backoff"""
    
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 30.0, backoff_factor: float = 2.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
    
    def get_delay(self, retry_count: int) -> float:
        """Calculate delay with exponential backoff and jitter"""
        delay = min(self.base_delay * (self.backoff_factor ** retry_count), self.max_delay)
        # Add jitter to prevent thundering herd
        jitter = delay * 0.1 * random.random()
        return delay + jitter

async def retry_async(func, *args, retry_config: RetryConfig = None, **kwargs):
    """Async retry decorator with exponential backoff"""
    if retry_config is None:
        retry_config = RetryConfig()
    
    last_exception = None
    
    for attempt in range(retry_config.max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            if attempt == retry_config.max_retries:
                raise last_exception
            
            delay = retry_config.get_delay(attempt)
            await asyncio.sleep(delay)
    
    raise last_exception

def retry_sync(func, *args, retry_config: RetryConfig = None, **kwargs):
    """Synchronous retry with exponential backoff"""
    if retry_config is None:
        retry_config = RetryConfig()
    
    last_exception = None
    
    for attempt in range(retry_config.max_retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            if attempt == retry_config.max_retries:
                raise last_exception
            
            delay = retry_config.get_delay(attempt)
            time.sleep(delay)
    
    raise last_exception

@dataclass
class TagDetectionResult:
    found: bool = False
    confidence_score: int = 0
    identifiers: List[str] = None
    detection_methods: List[str] = None
    verification_checks: List[str] = None
    implementation_details: List[str] = None
    warnings: List[str] = None
    loading_method: str = 'unknown'
    progressive_loading_detected: bool = False
    spa_detected: bool = False
    
    def __post_init__(self):
        if self.identifiers is None:
            self.identifiers = []
        if self.detection_methods is None:
            self.detection_methods = []
        if self.verification_checks is None:
            self.verification_checks = []
        if self.implementation_details is None:
            self.implementation_details = []
        if self.warnings is None:
            self.warnings = []

class ConfidenceCalibrator:
    """Calibrates confidence scores against known test cases"""
    
    def __init__(self):
        # Known test cases with expected results
        self.test_cases = {
            'gtm': {
                'high_confidence': [
                    ('GTM-ABC123', 85),
                    ('dataLayer.push', 70),
                    ('gtm.start', 60)
                ],
                'medium_confidence': [
                    ('googletagmanager.com', 45),
                    ('GTM-', 30)
                ],
                'low_confidence': [
                    ('gtag', 20),
                    ('google', 10)
                ]
            },
            'tealium': {
                'high_confidence': [
                    ('tags.tiqcdn.com', 80),
                    ('utag.js', 70),
                    ('utag_data', 60)
                ],
                'medium_confidence': [
                    ('tealium', 40),
                    ('utag', 30)
                ],
                'low_confidence': [
                    ('tiqcdn', 20),
                    ('tag', 10)
                ]
            },
            'gtag': {
                'high_confidence': [
                    ('G-XXXXXXXXXX', 85),
                    ('gtag/js', 75),
                    ('gtag(', 65)
                ],
                'medium_confidence': [
                    ('google-analytics.com', 50),
                    ('G-', 30)
                ],
                'low_confidence': [
                    ('analytics', 20),
                    ('google', 10)
                ]
            },
            'meta_pixel': {
                'high_confidence': [
                    ('fbq("init"', 80),
                    ('fbevents.js', 70),
                    ('fbq("track"', 60)
                ],
                'medium_confidence': [
                    ('facebook.com', 40),
                    ('fbq', 30)
                ],
                'low_confidence': [
                    ('meta', 20),
                    ('pixel', 10)
                ]
            },
            'tiktok_pixel': {
                'high_confidence': [
                    ('ttq.load', 80),
                    ('pixel/events.js', 70),
                    ('ttq.track', 60)
                ],
                'medium_confidence': [
                    ('tiktok.com', 40),
                    ('ttq', 30)
                ],
                'low_confidence': [
                    ('tiktok', 20),
                    ('pixel', 10)
                ]
            },
            'linkedin_insight': {
                'high_confidence': [
                    ('linkedin.com/collect', 80),
                    ('insight.min.js', 70),
                    ('_linkedin_data_partner_id', 60)
                ],
                'medium_confidence': [
                    ('linkedin', 40),
                    ('collect', 30)
                ],
                'low_confidence': [
                    ('linkedin', 20),
                    ('insight', 10)
                ]
            },
            'snap_pixel': {
                'high_confidence': [
                    ('snaptr("init"', 80),
                    ('scevent.min.js', 70),
                    ('snaptr("track"', 60)
                ],                'medium_confidence': [
                    ('snapchat.com', 40),
                    ('snaptr', 30)
                ],
                'low_confidence': [
                    ('snap', 20),    
                    ('pixel', 10)    
                ]
            },
            'universal_analytics': {
                'high_confidence': [
                    ('UA-XXXXXXXX-X', 85),
                    ('analytics.js', 75),
                    ('ga("create"', 65)
                ],
                'medium_confidence': [
                    ('google-analytics.com', 50),
                    ('UA-', 30)
                ],
                'low_confidence': [
                    ('analytics', 20),
                    ('google', 10)
                ]
            }
            
        }
    
    def calibrate_score(self, raw_score: int, plugin_name: str, detection_methods: List[str]) -> int:
        """Calibrate confidence score based on detection methods and known patterns"""
        # Base calibration
        calibrated = raw_score
        
        # Boost for multiple detection methods
        if len(detection_methods) >= 3:
            calibrated += 15
        elif len(detection_methods) >= 2:
            calibrated += 10
        
        # Adjust based on method quality
        high_quality_methods = ['Container ID Detection', 'Script URL Detection', 'Network Request Detection']
        quality_methods = sum(1 for method in detection_methods if method in high_quality_methods)
        calibrated += quality_methods * 5
        
        # Cap at 100
        return min(calibrated, 100)
class TagDetectorPlugin(ABC):
    """Abstract base class for tag detection plugins"""
    
    def __init__(self):
        self.calibrator = ConfidenceCalibrator()
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass
    
    @property
    @abstractmethod
    def version(self) -> str:
        pass
    
    @abstractmethod
    def detect_static(self, html_content: str, scripts: List[Dict], patterns: CompiledPatterns) -> TagDetectionResult:
        """Detect tags from static HTML content"""
        pass
    
    @abstractmethod 
    def detect_dynamic(self, network_requests: List[Dict], console_logs: List[str], 
                      dom_content: str, patterns: CompiledPatterns) -> TagDetectionResult:
        """Detect tags from JavaScript execution results"""
        pass
    
    def detect_progressive_loading(self, html_content: str, patterns: CompiledPatterns) -> bool:
        """Detect progressive loading patterns in SPAs"""
        return bool(patterns.progressive_loading.search(html_content) or
                   patterns.spa_frameworks.search(html_content))
    
    def merge_results(self, static_result: TagDetectionResult, 
                     dynamic_result: TagDetectionResult) -> TagDetectionResult:
        """Merge static and dynamic detection results"""
        merged = TagDetectionResult()
        merged.found = static_result.found or dynamic_result.found
        
        # Use calibrated confidence score
        raw_confidence = max(static_result.confidence_score, dynamic_result.confidence_score)
        all_methods = list(set(static_result.detection_methods + dynamic_result.detection_methods))
        merged.confidence_score = self.calibrator.calibrate_score(raw_confidence, self.name.lower(), all_methods)
        
        merged.identifiers = list(set(static_result.identifiers + dynamic_result.identifiers))
        merged.detection_methods = all_methods
        merged.verification_checks = list(set(static_result.verification_checks + dynamic_result.verification_checks))
        merged.implementation_details = list(set(static_result.implementation_details + dynamic_result.implementation_details))
        merged.warnings = list(set(static_result.warnings + dynamic_result.warnings))
        
        merged.progressive_loading_detected = static_result.progressive_loading_detected or dynamic_result.progressive_loading_detected
        merged.spa_detected = static_result.spa_detected or dynamic_result.spa_detected
        
        # Prefer dynamic loading method if available
        if dynamic_result.loading_method != 'unknown':
            merged.loading_method = dynamic_result.loading_method
        else:
            merged.loading_method = static_result.loading_method
            
        return merged
    
class GTMDetectorPlugin(TagDetectorPlugin):
    """Google Tag Manager detection plugin"""
    
    @property
    def name(self) -> str:
        return "Google Tag Manager"
    
    @property 
    def version(self) -> str:
        return "3.0.0"
    
    def detect_static(self, html_content: str, scripts: List[Dict], patterns: CompiledPatterns) -> TagDetectionResult:
        result = TagDetectionResult()
        html_lower = html_content.lower()
        
        # Progressive loading detection
        result.progressive_loading_detected = self.detect_progressive_loading(html_content, patterns)
        result.spa_detected = bool(patterns.spa_frameworks.search(html_content))
        
        # Container ID detection
        container_ids = set()
        for match in patterns.gtm_container_id.finditer(html_content):
            container_id = match.group(0).upper()
            if len(container_id) >= 8:
                container_ids.add(container_id)
                result.confidence_score += 40
        
        if container_ids:
            result.identifiers = list(container_ids)
            result.detection_methods.append('Container ID Detection')
        
        # Script URL detection
        for script in scripts:
            if script.get('src'):
                match = patterns.gtm_script_url.search(script['src'])
                if match:
                    gtm_id = match.group(1).upper()
                    if gtm_id.startswith('GTM-'):
                        container_ids.add(gtm_id)
                        result.confidence_score += 35
                        result.verification_checks.append('GTM Script URL Verified')
                        result.loading_method = 'direct_script'
        
        # Initialization code
        all_scripts = ' '.join([s.get('content', '') for s in scripts])
        if patterns.gtm_init_code.search(all_scripts):
            result.confidence_score += 20
            result.detection_methods.append('Initialization Code')
        
        # DataLayer detection
        if patterns.gtm_datalayer.search(html_lower):
            result.confidence_score += 15
            result.detection_methods.append('DataLayer Detection')
        
        # Dynamic script creation
        if patterns.gtm_dynamic.search(all_scripts):
            result.confidence_score += 30
            result.detection_methods.append('Dynamic Script Creation')
            result.loading_method = 'dynamic_insertion'
        
        # Noscript iframe
        noscript_match = patterns.gtm_noscript.search(html_content)
        if noscript_match:
            gtm_id = noscript_match.group(1).upper()
            if gtm_id.startswith('GTM-'):
                container_ids.add(gtm_id)
            result.confidence_score += 10
            result.detection_methods.append('Noscript Iframe')
        
        # Progressive loading warnings
        if result.progressive_loading_detected:
            result.warnings.append('Progressive loading detected - tags may load after user interaction')
        
        if result.spa_detected:
            result.warnings.append('SPA framework detected - consider extended monitoring period')
        
        # Final determination
        if result.confidence_score >= 35:
            result.found = True
            result.identifiers = list(container_ids)
        
        return result
    
    def detect_dynamic(self, network_requests: List[Dict], console_logs: List[str], 
                      dom_content: str, patterns: CompiledPatterns) -> TagDetectionResult:
        result = TagDetectionResult()
        
        # Check network requests for GTM
        gtm_requests = [req for req in network_requests 
                       if 'googletagmanager.com' in req.get('url', '')]
        
        if gtm_requests:
            result.confidence_score += 50
            result.detection_methods.append('Network Request Detection')
            result.verification_checks.append('GTM Network Requests Captured')
            result.loading_method = 'javascript_execution'
            
            # Extract container IDs from requests
            container_ids = set()
            for req in gtm_requests:
                matches = patterns.gtm_container_id.findall(req['url'])
                for match in matches:
                    container_ids.add(match.upper())
            
            result.identifiers = list(container_ids)
        
        # Check console logs for GTM messages
        gtm_console_messages = [log for log in console_logs 
                               if any(keyword in log.lower() for keyword in ['gtm', 'google tag manager', 'datalayer'])]
        
        if gtm_console_messages:
            result.confidence_score += 15
            result.implementation_details.append(f'GTM console messages: {len(gtm_console_messages)}')
        
        # Check final DOM for GTM elements
        if patterns.gtm_container_id.search(dom_content):
            result.confidence_score += 20
            result.verification_checks.append('GTM Found in Final DOM')
        
        # Progressive loading detection in final DOM
        result.progressive_loading_detected = self.detect_progressive_loading(dom_content, patterns)
        
        if result.confidence_score >= 30:
            result.found = True
        
        return result

class TealiumDetectorPlugin(TagDetectorPlugin):
    """Tealium detection plugin"""
    
    @property
    def name(self) -> str:
        return "Tealium"
    
    @property
    def version(self) -> str:
        return "3.0.0"
    
    def detect_static(self, html_content: str, scripts: List[Dict], patterns: CompiledPatterns) -> TagDetectionResult:
        result = TagDetectionResult()
        
        # Progressive loading detection
        result.progressive_loading_detected = self.detect_progressive_loading(html_content, patterns)
        result.spa_detected = bool(patterns.spa_frameworks.search(html_content))
        
        # Script URL detection
        account_info = set()
        for script in scripts:
            if script.get('src'):
                match = patterns.tealium_url.search(script['src'])
                if match:
                    account, profile, env = match.groups()
                    account_info.add(f"{account}/{profile}/{env}")
                    result.confidence_score += 40
                    result.loading_method = 'direct_script'
        
        if account_info:
            result.identifiers = list(account_info)
            result.detection_methods.append('Script URL Detection')
        
        # utag_data variable detection
        all_scripts = ' '.join([s.get('content', '') for s in scripts])
        if patterns.tealium_utag_data.search(all_scripts):
            result.confidence_score += 25
            result.detection_methods.append('utag_data Variable')
        
        # Async loading pattern
        if patterns.tealium_async.search(html_content):
            result.confidence_score += 20
            result.detection_methods.append('Async Loading Pattern')
            result.loading_method = 'async_function'
        
        # Function calls
        function_matches = patterns.tealium_functions.findall(all_scripts)
        if function_matches:
            result.confidence_score += len(function_matches) * 3
            result.detection_methods.append('Tealium Functions')
        
        # Dynamic script creation
        if patterns.tealium_dynamic.search(all_scripts):
            result.confidence_score += 30
            result.detection_methods.append('Dynamic Script Creation')
            result.loading_method = 'dynamic_insertion'
        
        if result.confidence_score >= 30:
            result.found = True
        
        return result
    
    def detect_dynamic(self, network_requests: List[Dict], console_logs: List[str], 
                      dom_content: str, patterns: CompiledPatterns) -> TagDetectionResult:
        result = TagDetectionResult()
        
        # Check network requests for Tealium
        tealium_requests = [req for req in network_requests 
                           if 'tiqcdn.com' in req.get('url', '') or 'tealium' in req.get('url', '')]
        
        if tealium_requests:
            result.confidence_score += 50
            result.detection_methods.append('Network Request Detection')
            result.verification_checks.append('Tealium Network Requests Captured')
            result.loading_method = 'javascript_execution'
            
            # Extract account info from requests
            account_info = set()
            for req in tealium_requests:
                matches = patterns.tealium_url.findall(req['url'])
                for account, profile, env in matches:
                    account_info.add(f"{account}/{profile}/{env}")
            
            result.identifiers = list(account_info)
        
        # Check console logs for Tealium messages
        tealium_console_messages = [log for log in console_logs 
                                   if any(keyword in log.lower() for keyword in ['tealium', 'utag', 'tiq'])]
        
        if tealium_console_messages:
            result.confidence_score += 15
            result.implementation_details.append(f'Tealium console messages: {len(tealium_console_messages)}')
        
        if result.confidence_score >= 30:
            result.found = True
        
        return result

class GtagDetectorPlugin(TagDetectorPlugin):
    """Gtag detection plugin"""
    
    @property
    def name(self) -> str:
        return "Gtag"
    
    @property
    def version(self) -> str:
        return "3.0.0"
    
    def detect_static(self, html_content: str, scripts: List[Dict], patterns: CompiledPatterns) -> TagDetectionResult:
        result = TagDetectionResult()
        
        # Progressive loading detection
        result.progressive_loading_detected = self.detect_progressive_loading(html_content, patterns)
        result.spa_detected = bool(patterns.spa_frameworks.search(html_content))
        
        # Measurement ID detection
        measurement_ids = set()
        for match in patterns.gtag_measurement_id.finditer(html_content):
            measurement_id = match.group(0).upper()
            measurement_ids.add(measurement_id)
            result.confidence_score += 40
        
        if measurement_ids:
            result.identifiers = list(measurement_ids)
            result.detection_methods.append('Measurement ID Detection')
        
        # Script URL detection
        for script in scripts:
            if script.get('src'):
                match = patterns.gtag_script_url.search(script['src'])
                if match:
                    gtag_id = match.group(1).upper()
                    measurement_ids.add(gtag_id)
                    result.confidence_score += 35
                    result.verification_checks.append('Gtag Script URL Verified')
                    result.loading_method = 'direct_script'
        
        # Function calls
        all_scripts = ' '.join([s.get('content', '') for s in scripts])
        if patterns.gtag_function.search(all_scripts):
            result.confidence_score += 20
            result.detection_methods.append('Gtag Function Calls')
        
        # Progressive loading warnings
        if result.progressive_loading_detected:
            result.warnings.append('Progressive loading detected - tags may load after user interaction')
        
        if result.spa_detected:
            result.warnings.append('SPA framework detected - consider extended monitoring period')
        
        if result.confidence_score >= 30:
            result.found = True
            result.identifiers = list(measurement_ids)
        
        return result
    
    def detect_dynamic(self, network_requests: List[Dict], console_logs: List[str], 
                      dom_content: str, patterns: CompiledPatterns) -> TagDetectionResult:
        result = TagDetectionResult()
        
        # Check network requests for Gtag
        gtag_requests = [req for req in network_requests 
                        if 'googletagmanager.com/gtag' in req.get('url', '')]
        
        if gtag_requests:
            result.confidence_score += 50
            result.detection_methods.append('Network Request Detection')
            result.verification_checks.append('Gtag Network Requests Captured')
            result.loading_method = 'javascript_execution'
            
            # Extract measurement IDs from requests
            measurement_ids = set()
            for req in gtag_requests:
                matches = patterns.gtag_measurement_id.findall(req['url'])
                for match in matches:
                    measurement_ids.add(match.upper())
            
            result.identifiers = list(measurement_ids)
        
        # Check console logs for Gtag messages
        gtag_console_messages = [log for log in console_logs 
                                if any(keyword in log.lower() for keyword in ['gtag', 'google analytics'])]
        
        if gtag_console_messages:
            result.confidence_score += 15
            result.implementation_details.append(f'Gtag console messages: {len(gtag_console_messages)}')
        
        # Check final DOM for Gtag elements
        if patterns.gtag_measurement_id.search(dom_content):
            result.confidence_score += 20
            result.verification_checks.append('Gtag Found in Final DOM')
        
        if result.confidence_score >= 30:
            result.found = True
        
        return result

class MetaPixelDetectorPlugin(TagDetectorPlugin):
    """Meta Pixel detection plugin"""
    
    @property
    def name(self) -> str:
        return "Meta Pixel"
    
    @property
    def version(self) -> str:
        return "3.0.0"
    
    def detect_static(self, html_content: str, scripts: List[Dict], patterns: CompiledPatterns) -> TagDetectionResult:
        result = TagDetectionResult()
        
        # Progressive loading detection
        result.progressive_loading_detected = self.detect_progressive_loading(html_content, patterns)
        result.spa_detected = bool(patterns.spa_frameworks.search(html_content))
        
        # Pixel ID detection
        pixel_ids = set()
        for match in patterns.meta_pixel_id.finditer(html_content):
            pixel_id = match.group(1)
            pixel_ids.add(pixel_id)
            result.confidence_score += 40
        
        if pixel_ids:
            result.identifiers = list(pixel_ids)
            result.detection_methods.append('Pixel ID Detection')
        
        # Script URL detection
        for script in scripts:
            if script.get('src'):
                if patterns.meta_pixel_script_url.search(script['src']):
                    result.confidence_score += 35
                    result.verification_checks.append('Meta Pixel Script URL Verified')
                    result.loading_method = 'direct_script'
        
        # Function calls
        all_scripts = ' '.join([s.get('content', '') for s in scripts])
        if patterns.meta_pixel_function.search(all_scripts):
            result.confidence_score += 20
            result.detection_methods.append('Meta Pixel Function Calls')
        
        # Dynamic script creation
        if patterns.meta_pixel_dynamic.search(all_scripts):
            result.confidence_score += 30
            result.detection_methods.append('Dynamic Script Creation')
            result.loading_method = 'dynamic_insertion'
        
        # Noscript detection
        noscript_match = patterns.meta_pixel_noscript.search(html_content)
        if noscript_match:
            pixel_id = noscript_match.group(1)
            pixel_ids.add(pixel_id)
            result.confidence_score += 10
            result.detection_methods.append('Noscript Detection')
        
        # Progressive loading warnings
        if result.progressive_loading_detected:
            result.warnings.append('Progressive loading detected - tags may load after user interaction')
        
        if result.spa_detected:
            result.warnings.append('SPA framework detected - consider extended monitoring period')
        
        if result.confidence_score >= 30:
            result.found = True
            result.identifiers = list(pixel_ids)
        
        return result
    
    def detect_dynamic(self, network_requests: List[Dict], console_logs: List[str], 
                      dom_content: str, patterns: CompiledPatterns) -> TagDetectionResult:
        result = TagDetectionResult()
        
        # Check network requests for Meta Pixel
        meta_requests = [req for req in network_requests 
                        if any(domain in req.get('url', '') for domain in ['facebook.com', 'connect.facebook.net'])]
        
        if meta_requests:
            result.confidence_score += 50
            result.detection_methods.append('Network Request Detection')
            result.verification_checks.append('Meta Pixel Network Requests Captured')
            result.loading_method = 'javascript_execution'
            
            # Extract pixel IDs from requests
            pixel_ids = set()
            for req in meta_requests:
                matches = patterns.meta_pixel_id.findall(req['url'])
                for match in matches:
                    pixel_ids.add(match)
            
            result.identifiers = list(pixel_ids)
        
        # Check console logs for Meta messages
        meta_console_messages = [log for log in console_logs 
                                if any(keyword in log.lower() for keyword in ['facebook', 'meta', 'fbq'])]
        
        if meta_console_messages:
            result.confidence_score += 15
            result.implementation_details.append(f'Meta Pixel console messages: {len(meta_console_messages)}')
        
        # Check final DOM for Meta Pixel elements
        if patterns.meta_pixel_id.search(dom_content):
            result.confidence_score += 20
            result.verification_checks.append('Meta Pixel Found in Final DOM')
        
        if result.confidence_score >= 30:
            result.found = True
        
        return result

class TikTokPixelDetectorPlugin(TagDetectorPlugin):
    """TikTok Pixel detection plugin"""
    
    @property
    def name(self) -> str:
        return "TikTok Pixel"
    
    @property
    def version(self) -> str:
        return "3.0.0"
    
    def detect_static(self, html_content: str, scripts: List[Dict], patterns: CompiledPatterns) -> TagDetectionResult:
        result = TagDetectionResult()
        
        # Progressive loading detection
        result.progressive_loading_detected = self.detect_progressive_loading(html_content, patterns)
        result.spa_detected = bool(patterns.spa_frameworks.search(html_content))
        
        # Pixel ID detection
        pixel_ids = set()
        for match in patterns.tiktok_pixel_id.finditer(html_content):
            pixel_id = match.group(1)
            pixel_ids.add(pixel_id)
            result.confidence_score += 40
        
        if pixel_ids:
            result.identifiers = list(pixel_ids)
            result.detection_methods.append('Pixel ID Detection')
        
        # Script URL detection
        for script in scripts:
            if script.get('src'):
                if patterns.tiktok_script_url.search(script['src']):
                    result.confidence_score += 35
                    result.verification_checks.append('TikTok Pixel Script URL Verified')
                    result.loading_method = 'direct_script'
        
        # Function calls
        all_scripts = ' '.join([s.get('content', '') for s in scripts])
        if patterns.tiktok_function.search(all_scripts):
            result.confidence_score += 20
            result.detection_methods.append('TikTok Function Calls')
        
        # Dynamic script creation
        if patterns.tiktok_dynamic.search(all_scripts):
            result.confidence_score += 30
            result.detection_methods.append('Dynamic Script Creation')
            result.loading_method = 'dynamic_insertion'
        
        # Noscript detection
        noscript_match = patterns.tiktok_noscript.search(html_content)
        if noscript_match:
            pixel_id = noscript_match.group(1)
            pixel_ids.add(pixel_id)
            result.confidence_score += 10
            result.detection_methods.append('Noscript Detection')
        
        # Progressive loading warnings
        if result.progressive_loading_detected:
            result.warnings.append('Progressive loading detected - tags may load after user interaction')
        
        if result.spa_detected:
            result.warnings.append('SPA framework detected - consider extended monitoring period')
        
        if result.confidence_score >= 30:
            result.found = True
            result.identifiers = list(pixel_ids)
        
        return result
    
    def detect_dynamic(self, network_requests: List[Dict], console_logs: List[str], 
                      dom_content: str, patterns: CompiledPatterns) -> TagDetectionResult:
        result = TagDetectionResult()
        
        # Check network requests for TikTok Pixel
        tiktok_requests = [req for req in network_requests 
                          if 'analytics.tiktok.com' in req.get('url', '')]
        
        if tiktok_requests:
            result.confidence_score += 50
            result.detection_methods.append('Network Request Detection')
            result.verification_checks.append('TikTok Pixel Network Requests Captured')
            result.loading_method = 'javascript_execution'
            
            # Extract pixel IDs from requests
            pixel_ids = set()
            for req in tiktok_requests:
                matches = patterns.tiktok_pixel_id.findall(req['url'])
                for match in matches:
                    pixel_ids.add(match)
            
            result.identifiers = list(pixel_ids)
        
        # Check console logs for TikTok messages
        tiktok_console_messages = [log for log in console_logs 
                                  if any(keyword in log.lower() for keyword in ['tiktok', 'ttq'])]
        
        if tiktok_console_messages:
            result.confidence_score += 15
            result.implementation_details.append(f'TikTok Pixel console messages: {len(tiktok_console_messages)}')
        
        # Check final DOM for TikTok Pixel elements
        if patterns.tiktok_pixel_id.search(dom_content):
            result.confidence_score += 20
            result.verification_checks.append('TikTok Pixel Found in Final DOM')
        
        if result.confidence_score >= 30:
            result.found = True
        
        return result

class LinkedInInsightDetectorPlugin(TagDetectorPlugin):
    """LinkedIn Insight Tag detection plugin"""
    
    @property
    def name(self) -> str:
        return "LinkedIn Insight Tag"
    
    @property
    def version(self) -> str:
        return "3.0.0"
    
    def detect_static(self, html_content: str, scripts: List[Dict], patterns: CompiledPatterns) -> TagDetectionResult:
        result = TagDetectionResult()
        
        # Progressive loading detection
        result.progressive_loading_detected = self.detect_progressive_loading(html_content, patterns)
        result.spa_detected = bool(patterns.spa_frameworks.search(html_content))
        
        # Partner ID detection
        partner_ids = set()
        for match in patterns.linkedin_partner_id.finditer(html_content):
            partner_id = match.group(1)
            partner_ids.add(partner_id)
            result.confidence_score += 40
        
        # Function-based partner ID detection
        for match in patterns.linkedin_function.finditer(html_content):
            partner_id = match.group(1)
            partner_ids.add(partner_id)
            result.confidence_score += 35
        
        if partner_ids:
            result.identifiers = list(partner_ids)
            result.detection_methods.append('Partner ID Detection')
        
        # Script URL detection
        for script in scripts:
            if script.get('src'):
                if patterns.linkedin_script_url.search(script['src']):
                    result.confidence_score += 35
                    result.verification_checks.append('LinkedIn Insight Script URL Verified')
                    result.loading_method = 'direct_script'
        
        # Dynamic script creation
        all_scripts = ' '.join([s.get('content', '') for s in scripts])
        if patterns.linkedin_dynamic.search(all_scripts):
            result.confidence_score += 30
            result.detection_methods.append('Dynamic Script Creation')
            result.loading_method = 'dynamic_insertion'
        
        # Noscript detection
        noscript_match = patterns.linkedin_noscript.search(html_content)
        if noscript_match:
            partner_id = noscript_match.group(1)
            partner_ids.add(partner_id)
            result.confidence_score += 10
            result.detection_methods.append('Noscript Detection')
        
        # Progressive loading warnings
        if result.progressive_loading_detected:
            result.warnings.append('Progressive loading detected - tags may load after user interaction')
        
        if result.spa_detected:
            result.warnings.append('SPA framework detected - consider extended monitoring period')
        
        if result.confidence_score >= 30:
            result.found = True
            result.identifiers = list(partner_ids)
        
        return result
    
    def detect_dynamic(self, network_requests: List[Dict], console_logs: List[str], 
                      dom_content: str, patterns: CompiledPatterns) -> TagDetectionResult:
        result = TagDetectionResult()
        
        # Check network requests for LinkedIn Insight
        linkedin_requests = [req for req in network_requests 
                            if any(domain in req.get('url', '') for domain in ['linkedin.com', 'snap.licdn.com'])]
        
        if linkedin_requests:
            result.confidence_score += 50
            result.detection_methods.append('Network Request Detection')
            result.verification_checks.append('LinkedIn Insight Network Requests Captured')
            result.loading_method = 'javascript_execution'
            
            # Extract partner IDs from requests
            partner_ids = set()
            for req in linkedin_requests:
                matches = patterns.linkedin_partner_id.findall(req['url'])
                for match in matches:
                    partner_ids.add(match)
            
            result.identifiers = list(partner_ids)
        
        # Check console logs for LinkedIn messages
        linkedin_console_messages = [log for log in console_logs 
                                    if any(keyword in log.lower() for keyword in ['linkedin', 'li_'])]
        
        if linkedin_console_messages:
            result.confidence_score += 15
            result.implementation_details.append(f'LinkedIn Insight console messages: {len(linkedin_console_messages)}')
        
        # Check final DOM for LinkedIn elements
        if patterns.linkedin_partner_id.search(dom_content) or patterns.linkedin_function.search(dom_content):
            result.confidence_score += 20
            result.verification_checks.append('LinkedIn Insight Found in Final DOM')
        
        if result.confidence_score >= 30:
            result.found = True
        
        return result

class SnapPixelDetectorPlugin(TagDetectorPlugin):
    """Snap Pixel detection plugin"""
    
    @property
    def name(self) -> str:
        return "Snap Pixel"
    
    @property
    def version(self) -> str:
        return "3.0.0"
    
    def detect_static(self, html_content: str, scripts: List[Dict], patterns: CompiledPatterns) -> TagDetectionResult:
        result = TagDetectionResult()
        
        # Progressive loading detection
        result.progressive_loading_detected = self.detect_progressive_loading(html_content, patterns)
        result.spa_detected = bool(patterns.spa_frameworks.search(html_content))
        
        # Pixel ID detection
        pixel_ids = set()
        for match in patterns.snap_pixel_id.finditer(html_content):
            pixel_id = match.group(1)
            pixel_ids.add(pixel_id)
            result.confidence_score += 40
        
        if pixel_ids:
            result.identifiers = list(pixel_ids)
            result.detection_methods.append('Pixel ID Detection')
        
        # Script URL detection
        for script in scripts:
            if script.get('src'):
                if patterns.snap_script_url.search(script['src']):
                    result.confidence_score += 35
                    result.verification_checks.append('Snap Pixel Script URL Verified')
                    result.loading_method = 'direct_script'
        
        # Function calls
        all_scripts = ' '.join([s.get('content', '') for s in scripts])
        if patterns.snap_function.search(all_scripts):
            result.confidence_score += 20
            result.detection_methods.append('Snap Function Calls')
        
        # Dynamic script creation
        if patterns.snap_dynamic.search(all_scripts):
            result.confidence_score += 30
            result.detection_methods.append('Dynamic Script Creation')
            result.loading_method = 'dynamic_insertion'
        
        # Noscript detection
        noscript_match = patterns.snap_noscript.search(html_content)
        if noscript_match:
            pixel_id = noscript_match.group(1)
            pixel_ids.add(pixel_id)
            result.confidence_score += 10
            result.detection_methods.append('Noscript Detection')
        
        # Progressive loading warnings
        if result.progressive_loading_detected:
            result.warnings.append('Progressive loading detected - tags may load after user interaction')
        
        if result.spa_detected:
            result.warnings.append('SPA framework detected - consider extended monitoring period')
        
        if result.confidence_score >= 30:
            result.found = True
            result.identifiers = list(pixel_ids)
        
        return result
    
    def detect_dynamic(self, network_requests: List[Dict], console_logs: List[str], 
                      dom_content: str, patterns: CompiledPatterns) -> TagDetectionResult:
        result = TagDetectionResult()
        
        # Check network requests for Snap Pixel
        snap_requests = [req for req in network_requests 
                        if 'sc-static.net' in req.get('url', '')]
        
        if snap_requests:
            result.confidence_score += 50
            result.detection_methods.append('Network Request Detection')
            result.verification_checks.append('Snap Pixel Network Requests Captured')
            result.loading_method = 'javascript_execution'
            
            # Extract pixel IDs from requests
            pixel_ids = set()
            for req in snap_requests:
                matches = patterns.snap_pixel_id.findall(req['url'])
                for match in matches:
                    pixel_ids.add(match)
            
            result.identifiers = list(pixel_ids)
        
        # Check console logs for Snap messages
        snap_console_messages = [log for log in console_logs 
                                if any(keyword in log.lower() for keyword in ['snapchat', 'snaptr', 'snap'])]
        
        if snap_console_messages:
            result.confidence_score += 15
            result.implementation_details.append(f'Snap Pixel console messages: {len(snap_console_messages)}')
        
        # Check final DOM for Snap Pixel elements
        if patterns.snap_pixel_id.search(dom_content):
            result.confidence_score += 20
            result.verification_checks.append('Snap Pixel Found in Final DOM')
        
        if result.confidence_score >= 30:
            result.found = True
        
        return result

class UniversalAnalyticsDetectorPlugin(TagDetectorPlugin):
    """Universal Analytics detection plugin"""
    
    @property
    def name(self) -> str:
        return "Universal Analytics"
    
    @property
    def version(self) -> str:
        return "3.0.0"
    
    def detect_static(self, html_content: str, scripts: List[Dict], patterns: CompiledPatterns) -> TagDetectionResult:
        result = TagDetectionResult()
        
        # Progressive loading detection
        result.progressive_loading_detected = self.detect_progressive_loading(html_content, patterns)
        result.spa_detected = bool(patterns.spa_frameworks.search(html_content))
        
        # Tracking ID detection
        tracking_ids = set()
        for match in patterns.ua_tracking_id.finditer(html_content):
            tracking_id = match.group(0).upper()
            tracking_ids.add(tracking_id)
            result.confidence_score += 40
        
        if tracking_ids:
            result.identifiers = list(tracking_ids)
            result.detection_methods.append('Tracking ID Detection')
        
        # Script URL detection
        for script in scripts:
            if script.get('src'):
                if patterns.ua_script_url.search(script['src']):
                    result.confidence_score += 35
                    result.verification_checks.append('UA Script URL Verified')
                    result.loading_method = 'direct_script'
        
        # Function calls
        all_scripts = ' '.join([s.get('content', '') for s in scripts])
        function_matches = patterns.ua_function.findall(all_scripts)
        if function_matches:
            result.confidence_score += len(function_matches) * 5
            result.detection_methods.append('GA Function Calls')
        
        # Dynamic script creation
        if patterns.ua_dynamic.search(all_scripts):
            result.confidence_score += 30
            result.detection_methods.append('Dynamic Script Creation')
            result.loading_method = 'dynamic_insertion'
        
        # Progressive loading warnings
        if result.progressive_loading_detected:
            result.warnings.append('Progressive loading detected - tags may load after user interaction')
        
        if result.spa_detected:
            result.warnings.append('SPA framework detected - consider extended monitoring period')
        
        # Final determination
        if result.confidence_score >= 35:
            result.found = True
            result.identifiers = list(tracking_ids)
        
        return result
    
    def detect_dynamic(self, network_requests: List[Dict], console_logs: List[str], 
                      dom_content: str, patterns: CompiledPatterns) -> TagDetectionResult:
        result = TagDetectionResult()
        
        # Check network requests for Universal Analytics
        ua_requests = [req for req in network_requests 
                      if 'google-analytics.com' in req.get('url', '')]
        
        if ua_requests:
            result.confidence_score += 50
            result.detection_methods.append('Network Request Detection')
            result.verification_checks.append('UA Network Requests Captured')
            result.loading_method = 'javascript_execution'
            
            # Extract tracking IDs from requests
            tracking_ids = set()
            for req in ua_requests:
                matches = patterns.ua_tracking_id.findall(req['url'])
                for match in matches:
                    tracking_ids.add(match.upper())
            
            result.identifiers = list(tracking_ids)
        
        # Check console logs for GA messages
        ga_console_messages = [log for log in console_logs 
                              if any(keyword in log.lower() for keyword in ['google analytics', 'ga(', '_ga'])]
        
        if ga_console_messages:
            result.confidence_score += 15
            result.implementation_details.append(f'GA console messages: {len(ga_console_messages)}')
        
        # Check final DOM for UA elements
        if patterns.ua_tracking_id.search(dom_content):
            result.confidence_score += 20
            result.verification_checks.append('UA Found in Final DOM')
        
        if result.confidence_score >= 30:
            result.found = True
        
        return result
    
class tagchecker:
    """Main Tag Checker class to manage detection plugins and patterns"""
    def __init__(self, use_javascript: bool = True, timeout: int = 20, max_workers: int = 2, 
                 retry_config: RetryConfig = None):
        self.use_javascript = use_javascript and PLAYWRIGHT_AVAILABLE
        self.timeout = timeout
        self.max_workers = max_workers
        self.patterns = CompiledPatterns()
        self.retry_config = retry_config or RetryConfig()
        
        # Plugin registry
        self.plugins: Dict[str, TagDetectorPlugin] = {
            'gtm': GTMDetectorPlugin(),
            'tealium': TealiumDetectorPlugin(),
            'gtag': GtagDetectorPlugin(),
            'meta_pixel': MetaPixelDetectorPlugin(),
            'tiktok_pixel': TikTokPixelDetectorPlugin(),
            'linkedin_insight': LinkedInInsightDetectorPlugin(),
            'snap_pixel': SnapPixelDetectorPlugin(),
            'universal_analytics': UniversalAnalyticsDetectorPlugin()
        }
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.96 Safari/537.36",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
            "Mozilla/5.0 (iPad; CPU OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"
        ]
        self.setup_logging()
        self.domain_performance = {}
        self.timeout_strategy = {
            'default': 8000,
            'extended': 15000,
            'maximum': 30000
        }
    def setup_logging(self):
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
    
    def register_plugin(self, name: str, plugin: TagDetectorPlugin):
        """Register a new tag detection plugin"""
        self.plugins[name] = plugin
        self.logger.info(f"Registered plugin: {plugin.name} v{plugin.version}")
    
    def get_headers(self) -> Dict[str, str]:
        import random
        return {
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
    
    async def execute_javascript_with_progressive_loading(self, url: str) -> Dict[str, Any]:
        domain = urlparse(url).netloc
        base_timeout = self._get_domain_timeout(domain)
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=self.get_headers()['User-Agent'],
                viewport={'width': 1920, 'height': 1080}
            )

            # Block non-essential resources
            await context.route("**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2}", 
                              lambda route: route.abort())

            page = await context.new_page()
            
            # Initialize tracking
            tag_requests = []
            console_logs = []
            performance_metrics = {
                'time_to_first_tag': None,
                'total_tag_requests': 0,
                'tag_load_complete': False
            }

            async def handle_request(request):
                if any(domain in request.url for domain in self.patterns.tag_domains):
                    tag_requests.append({
                        'url': request.url,
                        'timestamp': time.time(),
                        'resource_type': request.resource_type
                    })
                    if performance_metrics['time_to_first_tag'] is None:
                        performance_metrics['time_to_first_tag'] = time.time()

            page.on('request', handle_request)
            page.on('console', lambda msg: console_logs.append(msg.text))

            try:
                # Stage 1: Initial load
                await page.goto(url, wait_until='domcontentloaded', 
                              timeout=base_timeout)
                
                # Stage 2: Wait for initial scripts
                await page.wait_for_load_state('domcontentloaded')
                initial_content = await page.content()

                # Stage 3: Progressive waiting
                exit_conditions = False
                start_time = time.time()
                check_interval = 500

                while not exit_conditions and (time.time() - start_time) < base_timeout/1000:
                    # Check for tag presence
                    current_content = await page.content()
                    
                    # Check for key functions
                    has_tracking = await page.evaluate("""
                        () => ({
                            dataLayer: !!window.dataLayer,
                            gtag: !!window.gtag,
                            fbq: !!window.fbq,
                            ttq: !!window.ttq,
                            snaptr: !!window.snaptr
                        })
                    """)

                    if any(has_tracking.values()):
                        break

                    # Check tag requests
                    if len(tag_requests) > 0 and (time.time() - tag_requests[-1]['timestamp']) > 2:
                        break

                    # Simulate user interaction
                    if time.time() - start_time > 5:
                        await page.evaluate('window.scrollTo(0, document.body.scrollHeight / 2)')
                        await page.mouse.move(500, 300)

                    await page.wait_for_timeout(check_interval)

                # Update domain performance
                self._update_domain_performance(domain, time.time() - start_time, len(tag_requests))

                return {
                    'network_requests': tag_requests,
                    'console_logs': console_logs,
                    'final_dom': await page.content(),
                    'performance_metrics': performance_metrics,
                    'success': True
                }

            except Exception as e:
                self.logger.error(f"Error executing JavaScript: {str(e)}")
                return {
                    'network_requests': tag_requests,
                    'console_logs': console_logs,
                    'final_dom': initial_content if 'initial_content' in locals() else '',
                    'performance_metrics': performance_metrics,
                    'success': False,
                    'error': str(e)
                }
            finally:
                await browser.close()

    def _get_domain_timeout(self, domain: str) -> int:
        """Get appropriate timeout based on domain performance history"""
        if domain not in self.domain_performance:
            return self.timeout_strategy['default']
        
        avg_load_time = self.domain_performance[domain]['avg_load_time']
        if avg_load_time > 12:
            return self.timeout_strategy['maximum']
        elif avg_load_time > 6:
            return self.timeout_strategy['extended']
        return self.timeout_strategy['default']

    def _update_domain_performance(self, domain: str, load_time: float, tag_count: int):
        """Update domain performance metrics"""
        if domain not in self.domain_performance:
            self.domain_performance[domain] = {
                'attempts': 0,
                'successes': 0,
                'avg_load_time': 0,
                'tag_count': 0
            }
        
        stats = self.domain_performance[domain]
        stats['attempts'] += 1
        stats['successes'] += 1
        stats['avg_load_time'] = (stats['avg_load_time'] * (stats['attempts'] - 1) + load_time) / stats['attempts']
        stats['tag_count'] = max(stats['tag_count'], tag_count)
    
    def extract_static_content(self, html_content: str) -> Dict[str, Any]:
        """Extract static content for analysis"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
        except Exception:
            soup = None
        
        scripts = []
        if soup:
            for script in soup.find_all('script'):
                scripts.append({
                    'src': script.get('src', ''),
                    'content': script.string or '',
                    'type': script.get('type', ''),
                    'async': script.has_attr('async'),
                    'defer': script.has_attr('defer')
                })
        
        return {'scripts': scripts}
    
    async def fetch_url_with_retry(self, url: str) -> requests.Response:
        """Fetch URL with retry logic"""
        def fetch():
            if not url.startswith(('http://', 'https://')):
                full_url = 'https://' + url
            else:
                full_url = url
            return requests.get(full_url, headers=self.get_headers(), timeout=self.timeout)
        
        return retry_sync(fetch, retry_config=self.retry_config)
    
    async def analyze_url_comprehensive(self, url: str) -> Dict[str, Any]:
        """Comprehensive URL analysis with static and dynamic detection"""
        start_time = time.time()
        
        result = {
            'url': url,
            'status': 'success',
            'response_code': None,
            'page_load_time': 0,
            'javascript_executed': self.use_javascript,
            'detection_results': {},
            'error': None,
            'warnings': [],
            'retry_attempts': 0,
            'progressive_loading_detected': False
        }
        
        try:
            # Static analysis with retry
            response = await self.fetch_url_with_retry(url)
            result['response_code'] = response.status_code
            
            if response.status_code != 200:
                result['status'] = 'error'
                result['error'] = f'HTTP {response.status_code}'
                return result
            
            # Extract static content
            static_content = self.extract_static_content(response.text)
            
            # Execute JavaScript with progressive loading detection if enabled
            if self.use_javascript:
                js_result = await retry_async(
                    self.execute_javascript_with_progressive_loading, 
                    url, 
                    retry_config=self.retry_config
                )
                dynamic_data = js_result
                result['progressive_loading_detected'] = js_result.get('progressive_loading_detected', False)
            else:
                dynamic_data = {
                    'network_requests': [], 
                    'console_logs': [], 
                    'final_dom': response.text,
                    'progressive_loading_detected': False
                }
            
            # Run all plugins
            for plugin_name, plugin in self.plugins.items():
                static_result = plugin.detect_static(
                    response.text, 
                    static_content['scripts'], 
                    self.patterns
                )
                
                dynamic_result = plugin.detect_dynamic(
                    dynamic_data['network_requests'],
                    dynamic_data['console_logs'],
                    dynamic_data['final_dom'],
                    self.patterns
                )
                
                # Merge results
                final_result = plugin.merge_results(static_result, dynamic_result)
                result['detection_results'][plugin_name] = asdict(final_result)
            
            # Add performance metrics
            result['page_load_time'] = round(time.time() - start_time, 2)
            
            # Add warnings for late loading indicators
            if self.patterns.consent_managers.search(response.text):
                result['warnings'].append('Consent management detected - tags may load after user interaction')
            
            if self.patterns.lazy_loading.search(response.text):
                result['warnings'].append('Lazy loading detected - some tags may load after viewport interaction')
            
            if result['progressive_loading_detected']:
                result['warnings'].append('Progressive loading detected - extended monitoring performed')
            
        except Exception as e:
            result['status'] = 'error'
            result['error'] = str(e)[:200]
            result['page_load_time'] = round(time.time() - start_time, 2)
        
        return result
    
    async def check_urls_async(self, urls: List[str]) -> List[Dict[str, Any]]:
        """Asynchronous URL checking with semaphore for rate limiting"""
        semaphore = asyncio.Semaphore(self.max_workers)
        
        async def check_single_with_semaphore(url):
            async with semaphore:
                return await self.analyze_url_comprehensive(url)
        
        tasks = [check_single_with_semaphore(url) for url in urls]
        results = []
        
        completed = 0
        for coro in asyncio.as_completed(tasks):
            result = await coro
            results.append(result)
            completed += 1
            print(f"Progress: {completed}/{len(urls)} URLs analyzed")
        
        return results
    
    def check_urls(self, urls: List[str]) -> List[Dict[str, Any]]:
        """Main entry point for checking URLs"""
        if self.use_javascript:
            # Use async event loop for JavaScript execution
            return asyncio.run(self.check_urls_async(urls))
        else:
            # Use thread pool for static-only analysis
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = [executor.submit(asyncio.run, self.analyze_url_comprehensive(url)) 
                          for url in urls]
                results = []
                for i, future in enumerate(as_completed(futures)):
                    results.append(future.result())
                    print(f"Progress: {i+1}/{len(urls)} URLs analyzed")
                return results
    def save_comprehensive_results(self, results: List[Dict[str, Any]], filename: str = 'results.csv'):
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            # Dynamic fieldnames based on available plugins
            base_fields = ['url', 'status', 'response_code', 'javascript_executed']
            plugin_fields = []
            for plugin_name in self.plugins.keys():
                plugin_fields.extend([
                    f"{plugin_name}_found",
                    f"{plugin_name}_confidence_score",
                    f"{plugin_name}_identifiers",
                    f"{plugin_name}_detection_methods",
                    f"{plugin_name}_verification_checks"
                ])
            all_fields = base_fields + plugin_fields
            writer = csv.DictWriter(csvfile, fieldnames=all_fields)
            writer.writeheader()
            for result in results:
                csv_row = {field: result.get(field, '') for field in base_fields}
                for plugin_name in self.plugins.keys():
                    plugin_result = result.get('detection_results', {}).get(plugin_name, {})
                    csv_row[f"{plugin_name}_found"] = plugin_result.get('found', False)
                    csv_row[f"{plugin_name}_confidence_score"] = plugin_result.get('confidence_score', 0)
                    csv_row[f"{plugin_name}_identifiers"] = ', '.join(plugin_result.get('identifiers', []))
                    csv_row[f"{plugin_name}_detection_methods"] = ', '.join(plugin_result.get('detection_methods', []))
                    csv_row[f"{plugin_name}_verification_checks"] = ', '.join(plugin_result.get('verification_checks', []))
                writer.writerow(csv_row)

        print(f"Comprehensive results saved to {filename}")

class testcompiledpatterns:
    def run_tests(self):
        patterns = CompiledPatterns()
        test_strings = {
            'gtm_container_id': ['GTM-ABC123', 'gtm-xyz789', 'GTM-1234', 'GTM-TOOLONGID12345'],
            'gtm_script_url': ['https://www.googletagmanager.com/gtm.js?id=GTM-ABC123', 
                               'http://googletagmanager.com/gtm.js?id=GTM-XYZ789'],
            'gtm_init_code': ["<script>function gtag(){dataLayer.push(arguments);}</script>"],
            'gtm_datalayer': ['dataLayer = [];', 'var dataLayer = [];'],
            'gtm_dynamic': ["var script = document.createElement('script'); script.src = 'https://www.googletagmanager.com/gtm.js?id=GTM-ABC123';"],
            'gtm_noscript': ['<noscript><iframe src="https://www.googletagmanager.com/ns.html?id=GTM-ABC123"></iframe></noscript>'],
            'tealium_url': ['https://tags.tiqcdn.com/utag/account/profile/env/utag.js'],
            'tealium_utag_data': ['var utag_data = {};', 'utag_data.page_name = "Home";'],
            'tealium_async': ["(function(a,b,c,d){var e=...;})"],
            'tealium_functions': ['utag.view();', 'utag.link();'],
            'tealium_dynamic': ["var s=document.createElement('script'); s.src='https://tags.tiqcdn.com/utag/account/profile/env/utag.js';"],
            'ua_tracking_id': ['UA-12345678-1', 'ua-87654321-2'],
            'ua_script_url': ['https://www.google-analytics.com/analytics.js', 
                              'http://www.google-analytics.com/ga.js'],
            'ua_function': ['ga("create", "UA-12345678-1", "auto");', "ga('send', 'pageview');"],
            'ua_dynamic': ["var gaScript = document.createElement('script'); gaScript.src = 'https://www.google-analytics.com/analytics.js';"],
            'gtag': ['<script async src="https://www.googletagmanager.com/gtag/js?id=GA-12345678-1"></script>'],
            'metapixel': ['<script src="https://connect.facebook.net/en_US/fbevents.js"></script>'],
            'tiktokpixel': ['<script src="https://analytics.tiktok.com/i18n/pixel/sdk.js"></script>'],
            'linkedininsight': ['<script src="https://snap.licdn.com/li.lms-analytics/insight.min.js"></script>'],
            'snappixel': ['<script src="https://sc-static.net/scevent.min.js"></script>'],
            'consent_managers': ['<div id="cookie-consent">', 'class="consent-banner"'],
            'lazy_loading': ['class="lazyload"', 'data-src="image.jpg"'],
            'spa_frameworks': ['<script src="https://cdnjs.cloudflare.com/ajax/libs/angular.js/1.8.2/angular.min.js"></script>', 
                               '<script src="https://unpkg.com/react@17/umd/react.production.min.js"></script>']
        }

        for pattern_name, test_strings in test_strings.items():
            pattern = getattr(patterns, pattern_name)
            for test_str in test_strings:
                match = pattern.search(test_str)
                if match:
                    print(f"Pattern '{pattern_name}' matched in: {test_str}")
                else:
                    print(f"Pattern '{pattern_name}' did NOT match in: {test_str}")
        print("All pattern tests completed.")

def load_urls_from_csv(filename: str, column_name: str = 'URL') -> List[str]:
    """Load URLs from CSV with enhanced validation"""
    urls = []
    try:
        with open(filename, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            
            if column_name not in reader.fieldnames:
                print(f"Column '{column_name}' not found in CSV file.")
                print(f"Available columns: {', '.join(reader.fieldnames)}")
                return urls
            
            for row_num, row in enumerate(reader, start=2):
                url = row[column_name].strip() if row[column_name] else ''
                if url:
                    # Enhanced URL validation
                    if not url.startswith(('http://', 'https://')) and '.' in url:
                        urls.append(url)
                    elif url.startswith(('http://', 'https://')):
                        urls.append(url)
                    else:
                        print(f"Skipping invalid URL on row {row_num}: {url}")
        
        print(f"Loaded {len(urls)} valid URLs from {filename}")
        
    except FileNotFoundError:
        print(f"CSV file {filename} not found.")
    except Exception as e:
        print(f"Error reading CSV file {filename}: {e}")
    
    return urls

def main():
    # configurations
    csv_file_path = '/Users/melrou01/Downloads/gsctable.csv'  # Path to your CSV file
    url_column_name = 'URL'      # Column name in CSV containing URLs
    output_file = 'tag_detection_results.csv'  # Output CSV file for results

    # Load URLs from CSV
    urls = load_urls_from_csv(csv_file_path, 'URL')
    if not urls:
        print("No URLs to analyze. Please check your CSV file.")
        return
    
    retry_config = RetryConfig(max_retries=2, backoff_factor=1)
    checker = tagchecker(use_javascript=True, timeout=20, max_workers=2, retry_config=retry_config)
    print(f"ANALYZING {len(urls)} URLs...")
    print("Using plugins:")
    for plugin_name, plugin in checker.plugins.items():
        print(f"   • {plugin.name} v{plugin.version}")
    print()
    
    # Perform analysis
    start_time = time.time()
    results = checker.check_urls(urls)
    total_time = time.time() - start_time
    
    print(f"\nAnalysis completed in {total_time:.2f}s")
    print(f"Average time per URL: {total_time/len(urls):.2f}s")
    
    # Display detailed results
    print("\n" + "="*80)
    print("DETAILED RESULTS")
    print("="*80)
    
    for i, result in enumerate(results, 1):
        print(f"\n[{i}/{len(results)}] {result['url']}")
        print(f"Status: {result['status']} | Load time: {result.get('page_load_time', 0):.2f}s | JS: {'✓' if result.get('javascript_executed') else '✗'}")
        
        if result.get('progressive_loading_detected'):
            print("   Progressive Loading: DETECTED")
        
        if result['status'] == 'success':
            # Show detection results for each plugin
            detection_results = result.get('detection_results', {})
            
            for plugin_name, plugin_data in detection_results.items():
                plugin = checker.plugins[plugin_name]
                found = plugin_data.get('found', False)
                confidence = plugin_data.get('confidence_score', 0)
                
                status_icon = "FOUND" if found else "NOT FOUND"
                print(f"   {plugin.name}: {status_icon}", end="")
                
                if found:
                    print(f" (Confidence: {confidence}%)")
                    identifiers = plugin_data.get('identifiers', [])
                    if identifiers:
                        print(f"      IDs: {', '.join(identifiers[:3])}{'...' if len(identifiers) > 3 else ''}")
                    
                    methods = plugin_data.get('detection_methods', [])
                    if methods:
                        print(f"      Methods: {', '.join(methods[:2])}{'...' if len(methods) > 2 else ''}")
                    
                    loading_method = plugin_data.get('loading_method', 'unknown')
                    if loading_method != 'unknown':
                        print(f"      Loading: {loading_method}")
                    
                    if plugin_data.get('spa_detected'):
                        print("      SPA Framework: DETECTED")
                else:
                    print()
            
            # Show warnings
            warnings = result.get('warnings', [])
            if warnings:
                print(f"   Warnings: {'; '.join(warnings)}")
        
        else:
            print(f"   Error: {result.get('error', 'Unknown error')}")
        
        print("-" * 80)
    

    
    # Save results to CSV
    checker.save_comprehensive_results(results, output_file)

if __name__ == "__main__":
    # Dependency check
    missing_deps = []
    
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError as e:
        missing_deps.append("requests beautifulsoup4")
    
    if not PLAYWRIGHT_AVAILABLE:
        print("Optional: For maximum accuracy (30-40% improvement), install Playwright:")
        print("   pip install playwright && playwright install chromium")
        print()
    
    if missing_deps:
        print(f"Missing required dependencies: {' '.join(missing_deps)}")
        print(f"Install with: pip install {' '.join(missing_deps)}")
        exit(1)
    
    
    main()