import asyncio
import re
import json
import time
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict

# Core dependencies
import requests
from bs4 import BeautifulSoup

# Headless browser dependencies (optional)
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("Warning: Playwright not installed. JavaScript execution disabled.")

# Compiled regex patterns for performance
class CompiledPatterns:
    def __init__(self):
        # GTM patterns
        self.gtm_container_id = re.compile(r'GTM-[A-Z0-9]{4,}', re.IGNORECASE)
        self.gtm_script_url = re.compile(r'https://www\.googletagmanager\.com/gtm\.js\?id=([^&"\'\s]+)', re.IGNORECASE)
        self.gtm_init_code = re.compile(r'gtm\.start["\']?\s*:\s*new\s+Date\(\)\.getTime\(\)', re.IGNORECASE | re.DOTALL)
        self.gtm_datalayer = re.compile(r'dataLayer\s*=\s*\[|dataLayer\.push\s*\(', re.IGNORECASE)
        self.gtm_noscript = re.compile(r'<noscript>.*?<iframe[^>]*src=["\']https://www\.googletagmanager\.com/ns\.html\?id=([^"\'&]+)', re.IGNORECASE | re.DOTALL)
        self.gtm_dynamic = re.compile(r'createElement\s*\(\s*["\']script["\'][\s\S]{0,200}?googletagmanager\.com/gtm\.js', re.IGNORECASE | re.DOTALL)
        
        # Tealium patterns
        self.tealium_url = re.compile(r'https://tags\.tiqcdn\.com/utag/([^/]+)/([^/]+)/([^/]+)/utag\.js', re.IGNORECASE)
        self.tealium_utag_data = re.compile(r'var\s+utag_data\s*=\s*\{|utag_data\s*=\s*\{', re.IGNORECASE)
        self.tealium_functions = re.compile(r'utag\.(link|view|track|sync)\s*\(', re.IGNORECASE)
        self.tealium_dynamic = re.compile(r'createElement\s*\(\s*["\']script["\'][\s\S]{0,300}?tags\.tiqcdn\.com', re.IGNORECASE | re.DOTALL)
        
        # gtag patterns
        self.gtag_measurement_id = re.compile(r'G-[A-Z0-9]{10}', re.IGNORECASE)
        self.gtag_script_url = re.compile(r'https://www\.googletagmanager\.com/gtag/js\?id=([^&"\'\s]+)', re.IGNORECASE)
        self.gtag_function = re.compile(r'gtag\s*\(\s*["\']config["\']|gtag\s*\(\s*["\']event["\']', re.IGNORECASE)

        # Meta Pixel patterns
        self.meta_pixel_id = re.compile(r'fbq\s*\(\s*["\']init["\']\s*,\s*["\'](\d{15,16})["\']', re.IGNORECASE)
        self.meta_pixel_script_url = re.compile(r'https://connect\.facebook\.net/[^/]+/fbevents\.js', re.IGNORECASE)
        self.meta_pixel_noscript = re.compile(r'<noscript>.*?<img[^>]*src=["\']https://www\.facebook\.com/tr\?id=(\d{15,16})', re.IGNORECASE | re.DOTALL)
        self.meta_pixel_function = re.compile(r'fbq\s*\(\s*["\']track["\']\s*,', re.IGNORECASE)

        # TikTok Pixel patterns
        self.tiktok_pixel_id = re.compile(r'ttq\.load\s*\(\s*["\']([^"\']+)["\']', re.IGNORECASE)
        self.tiktok_script_url = re.compile(r'https://analytics\.tiktok\.com/i18n/pixel/events\.js', re.IGNORECASE)
        self.tiktok_function = re.compile(r'ttq\.track\s*\(\s*["\']([^"\']+)["\']', re.IGNORECASE)

        # LinkedIn Insight patterns
        self.linkedin_partner_id = re.compile(r'linkedin\.com\/collect\?pid=(\d+)', re.IGNORECASE)
        self.linkedin_script_url = re.compile(r'https://snap.licdn.com/li.lms-analytics/insight\.min\.js', re.IGNORECASE)
        self.linkedin_function = re.compile(r'_linkedin_data_partner_id\s*=\s*["\'](\d+)["\']', re.IGNORECASE)

        # Snap Pixel patterns
        self.snap_pixel_id = re.compile(r'snaptr\s*\(\s*["\']init["\']\s*,\s*["\']([^"\']+)["\']', re.IGNORECASE)
        self.snap_script_url = re.compile(r'https://sc-static\.net/scevent.min\.js', re.IGNORECASE)
        self.snap_function = re.compile(r'snaptr\s*\(\s*["\']track["\']\s*,', re.IGNORECASE)

        # Universal Analytics patterns
        self.ua_tracking_id = re.compile(r'UA-\d{4,10}-\d{1,4}', re.IGNORECASE)
        self.ua_script_url = re.compile(r'https://www\.google-analytics\.com/analytics\.js', re.IGNORECASE)
        self.ua_function = re.compile(r'ga\s*\(\s*["\']create["\']|ga\s*\(\s*["\']send["\']', re.IGNORECASE)

        # SPA and progressive loading patterns
        self.spa_frameworks = re.compile(r'react|angular|vue|next\.js|nuxt|gatsby|svelte', re.IGNORECASE)
        self.progressive_loading = re.compile(r'intersectionobserver|requestidlecallback|loading\s*=\s*["\']lazy["\']', re.IGNORECASE)
        self.consent_managers = re.compile(r'cookiebot|onetrust|usercentrics|trustarc|iubenda', re.IGNORECASE)
        
        # Tag domains for network monitoring
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

class SingleUrlTagChecker:
    """Simplified tag checker for single URL analysis"""
    
    def __init__(self, use_javascript: bool = True, timeout: int = 20):
        self.use_javascript = use_javascript and PLAYWRIGHT_AVAILABLE
        self.timeout = timeout
        self.patterns = CompiledPatterns()
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    
    def get_headers(self) -> Dict[str, str]:
        return {
            'User-Agent': self.user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
    
    def detect_progressive_loading(self, html_content: str) -> bool:
        """Detect progressive loading patterns in SPAs"""
        return bool(self.patterns.progressive_loading.search(html_content) or
                   self.patterns.spa_frameworks.search(html_content))
    
    def extract_scripts(self, html_content: str) -> List[Dict]:
        """Extract script elements from HTML"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
        except Exception:
            return []
        
        scripts = []
        for script in soup.find_all('script'):
            scripts.append({
                'src': script.get('src', ''),
                'content': script.string or '',
                'type': script.get('type', ''),
                'async': script.has_attr('async'),
                'defer': script.has_attr('defer')
            })
        return scripts
    
    def detect_gtm(self, html_content: str, scripts: List[Dict], 
                   network_requests: List[Dict] = None) -> TagDetectionResult:
        """Detect Google Tag Manager"""
        result = TagDetectionResult()
        
        # Progressive loading detection
        result.progressive_loading_detected = self.detect_progressive_loading(html_content)
        result.spa_detected = bool(self.patterns.spa_frameworks.search(html_content))
        
        # Container ID detection
        container_ids = set()
        for match in self.patterns.gtm_container_id.finditer(html_content):
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
                match = self.patterns.gtm_script_url.search(script['src'])
                if match:
                    gtm_id = match.group(1).upper()
                    if gtm_id.startswith('GTM-'):
                        container_ids.add(gtm_id)
                        result.confidence_score += 35
                        result.verification_checks.append('GTM Script URL Verified')
                        result.loading_method = 'direct_script'
        
        # Other detections
        all_scripts = ' '.join([s.get('content', '') for s in scripts])
        if self.patterns.gtm_init_code.search(all_scripts):
            result.confidence_score += 20
            result.detection_methods.append('Initialization Code')
        
        if self.patterns.gtm_datalayer.search(html_content.lower()):
            result.confidence_score += 15
            result.detection_methods.append('DataLayer Detection')
        
        # Network requests (if available)
        if network_requests:
            gtm_requests = [req for req in network_requests 
                           if 'googletagmanager.com' in req.get('url', '')]
            if gtm_requests:
                result.confidence_score += 50
                result.detection_methods.append('Network Request Detection')
                result.loading_method = 'javascript_execution'
        
        if result.confidence_score >= 35:
            result.found = True
            result.identifiers = list(container_ids)
        
        return result
    
    def detect_tealium(self, html_content: str, scripts: List[Dict], 
                      network_requests: List[Dict] = None) -> TagDetectionResult:
        """Detect Tealium"""
        result = TagDetectionResult()
        
        # Script URL detection
        account_info = set()
        for script in scripts:
            if script.get('src'):
                match = self.patterns.tealium_url.search(script['src'])
                if match:
                    account, profile, env = match.groups()
                    account_info.add(f"{account}/{profile}/{env}")
                    result.confidence_score += 40
                    result.loading_method = 'direct_script'
        
        if account_info:
            result.identifiers = list(account_info)
            result.detection_methods.append('Script URL Detection')
        
        # utag_data detection
        all_scripts = ' '.join([s.get('content', '') for s in scripts])
        if self.patterns.tealium_utag_data.search(all_scripts):
            result.confidence_score += 25
            result.detection_methods.append('utag_data Variable')
        
        # Function calls
        function_matches = self.patterns.tealium_functions.findall(all_scripts)
        if function_matches:
            result.confidence_score += len(function_matches) * 3
            result.detection_methods.append('Tealium Functions')
        
        # Network requests
        if network_requests:
            tealium_requests = [req for req in network_requests 
                               if 'tiqcdn.com' in req.get('url', '')]
            if tealium_requests:
                result.confidence_score += 50
                result.detection_methods.append('Network Request Detection')
        
        if result.confidence_score >= 30:
            result.found = True
        
        return result
    
    def detect_gtag(self, html_content: str, scripts: List[Dict], 
                   network_requests: List[Dict] = None) -> TagDetectionResult:
        """Detect gtag"""
        result = TagDetectionResult()
        
        # Measurement ID detection
        measurement_ids = set()
        for match in self.patterns.gtag_measurement_id.finditer(html_content):
            measurement_id = match.group(0).upper()
            measurement_ids.add(measurement_id)
            result.confidence_score += 40
        
        if measurement_ids:
            result.identifiers = list(measurement_ids)
            result.detection_methods.append('Measurement ID Detection')
        
        # Script URL detection
        for script in scripts:
            if script.get('src'):
                match = self.patterns.gtag_script_url.search(script['src'])
                if match:
                    gtag_id = match.group(1).upper()
                    measurement_ids.add(gtag_id)
                    result.confidence_score += 35
                    result.verification_checks.append('Gtag Script URL Verified')
                    result.loading_method = 'direct_script'
        
        # Function calls
        all_scripts = ' '.join([s.get('content', '') for s in scripts])
        if self.patterns.gtag_function.search(all_scripts):
            result.confidence_score += 20
            result.detection_methods.append('Gtag Function Calls')
        
        if result.confidence_score >= 30:
            result.found = True
            result.identifiers = list(measurement_ids)
        
        return result
    
    def detect_meta_pixel(self, html_content: str, scripts: List[Dict], 
                         network_requests: List[Dict] = None) -> TagDetectionResult:
        """Detect Meta Pixel"""
        result = TagDetectionResult()
        
        # Pixel ID detection
        pixel_ids = set()
        for match in self.patterns.meta_pixel_id.finditer(html_content):
            pixel_id = match.group(1)
            pixel_ids.add(pixel_id)
            result.confidence_score += 40
        
        if pixel_ids:
            result.identifiers = list(pixel_ids)
            result.detection_methods.append('Pixel ID Detection')
        
        # Script URL detection
        for script in scripts:
            if script.get('src'):
                if self.patterns.meta_pixel_script_url.search(script['src']):
                    result.confidence_score += 35
                    result.verification_checks.append('Meta Pixel Script URL Verified')
                    result.loading_method = 'direct_script'
        
        # Function calls
        all_scripts = ' '.join([s.get('content', '') for s in scripts])
        if self.patterns.meta_pixel_function.search(all_scripts):
            result.confidence_score += 20
            result.detection_methods.append('Meta Pixel Function Calls')
        
        # Network requests
        if network_requests:
            meta_requests = [req for req in network_requests 
                            if any(domain in req.get('url', '') for domain in ['facebook.com', 'connect.facebook.net'])]
            if meta_requests:
                result.confidence_score += 50
                result.detection_methods.append('Network Request Detection')
        
        if result.confidence_score >= 30:
            result.found = True
            result.identifiers = list(pixel_ids)
        
        return result
    
    def detect_tiktok_pixel(self, html_content: str, scripts: List[Dict], 
                           network_requests: List[Dict] = None) -> TagDetectionResult:
        """Detect TikTok Pixel"""
        result = TagDetectionResult()
        
        # Pixel ID detection
        pixel_ids = set()
        for match in self.patterns.tiktok_pixel_id.finditer(html_content):
            pixel_id = match.group(1)
            pixel_ids.add(pixel_id)
            result.confidence_score += 40
        
        if pixel_ids:
            result.identifiers = list(pixel_ids)
            result.detection_methods.append('Pixel ID Detection')
        
        # Script URL detection
        for script in scripts:
            if script.get('src'):
                if self.patterns.tiktok_script_url.search(script['src']):
                    result.confidence_score += 35
                    result.verification_checks.append('TikTok Pixel Script URL Verified')
                    result.loading_method = 'direct_script'
        
        # Function calls
        all_scripts = ' '.join([s.get('content', '') for s in scripts])
        if self.patterns.tiktok_function.search(all_scripts):
            result.confidence_score += 20
            result.detection_methods.append('TikTok Function Calls')
        
        # Network requests
        if network_requests:
            tiktok_requests = [req for req in network_requests 
                              if 'analytics.tiktok.com' in req.get('url', '')]
            if tiktok_requests:
                result.confidence_score += 50
                result.detection_methods.append('Network Request Detection')
        
        if result.confidence_score >= 30:
            result.found = True
            result.identifiers = list(pixel_ids)
        
        return result
    
    def detect_linkedin_insight(self, html_content: str, scripts: List[Dict], 
                               network_requests: List[Dict] = None) -> TagDetectionResult:
        """Detect LinkedIn Insight Tag"""
        result = TagDetectionResult()
        
        # Partner ID detection
        partner_ids = set()
        for match in self.patterns.linkedin_partner_id.finditer(html_content):
            partner_id = match.group(1)
            partner_ids.add(partner_id)
            result.confidence_score += 40
        
        # Function-based partner ID detection
        for match in self.patterns.linkedin_function.finditer(html_content):
            partner_id = match.group(1)
            partner_ids.add(partner_id)
            result.confidence_score += 35
        
        if partner_ids:
            result.identifiers = list(partner_ids)
            result.detection_methods.append('Partner ID Detection')
        
        # Script URL detection
        for script in scripts:
            if script.get('src'):
                if self.patterns.linkedin_script_url.search(script['src']):
                    result.confidence_score += 35
                    result.verification_checks.append('LinkedIn Insight Script URL Verified')
                    result.loading_method = 'direct_script'
        
        # Network requests
        if network_requests:
            linkedin_requests = [req for req in network_requests 
                                if any(domain in req.get('url', '') for domain in ['linkedin.com', 'snap.licdn.com'])]
            if linkedin_requests:
                result.confidence_score += 50
                result.detection_methods.append('Network Request Detection')
        
        if result.confidence_score >= 30:
            result.found = True
            result.identifiers = list(partner_ids)
        
        return result
    
    def detect_snap_pixel(self, html_content: str, scripts: List[Dict], 
                         network_requests: List[Dict] = None) -> TagDetectionResult:
        """Detect Snap Pixel"""
        result = TagDetectionResult()
        
        # Pixel ID detection
        pixel_ids = set()
        for match in self.patterns.snap_pixel_id.finditer(html_content):
            pixel_id = match.group(1)
            pixel_ids.add(pixel_id)
            result.confidence_score += 40
        
        if pixel_ids:
            result.identifiers = list(pixel_ids)
            result.detection_methods.append('Pixel ID Detection')
        
        # Script URL detection
        for script in scripts:
            if script.get('src'):
                if self.patterns.snap_script_url.search(script['src']):
                    result.confidence_score += 35
                    result.verification_checks.append('Snap Pixel Script URL Verified')
                    result.loading_method = 'direct_script'
        
        # Function calls
        all_scripts = ' '.join([s.get('content', '') for s in scripts])
        if self.patterns.snap_function.search(all_scripts):
            result.confidence_score += 20
            result.detection_methods.append('Snap Function Calls')
        
        # Network requests
        if network_requests:
            snap_requests = [req for req in network_requests 
                            if 'sc-static.net' in req.get('url', '')]
            if snap_requests:
                result.confidence_score += 50
                result.detection_methods.append('Network Request Detection')
        
        if result.confidence_score >= 30:
            result.found = True
            result.identifiers = list(pixel_ids)
        
        return result
    
    def detect_universal_analytics(self, html_content: str, scripts: List[Dict], 
                                  network_requests: List[Dict] = None) -> TagDetectionResult:
        """Detect Universal Analytics"""
        result = TagDetectionResult()
        
        # Tracking ID detection
        tracking_ids = set()
        for match in self.patterns.ua_tracking_id.finditer(html_content):
            tracking_id = match.group(0).upper()
            tracking_ids.add(tracking_id)
            result.confidence_score += 40
        
        if tracking_ids:
            result.identifiers = list(tracking_ids)
            result.detection_methods.append('Tracking ID Detection')
        
        # Script URL detection
        for script in scripts:
            if script.get('src'):
                if self.patterns.ua_script_url.search(script['src']):
                    result.confidence_score += 35
                    result.verification_checks.append('UA Script URL Verified')
                    result.loading_method = 'direct_script'
        
        # Function calls
        all_scripts = ' '.join([s.get('content', '') for s in scripts])
        function_matches = self.patterns.ua_function.findall(all_scripts)
        if function_matches:
            result.confidence_score += len(function_matches) * 5
            result.detection_methods.append('GA Function Calls')
        
        # Network requests
        if network_requests:
            ua_requests = [req for req in network_requests 
                          if 'google-analytics.com' in req.get('url', '')]
            if ua_requests:
                result.confidence_score += 50
                result.detection_methods.append('Network Request Detection')
        
        if result.confidence_score >= 35:
            result.found = True
            result.identifiers = list(tracking_ids)
        
        return result
    
    async def execute_javascript(self, url: str) -> Dict[str, Any]:
        """Execute JavaScript and capture network requests"""
        if not self.use_javascript:
            return {'network_requests': [], 'console_logs': [], 'final_dom': ''}
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=self.user_agent)
            
            # Block images and stylesheets for faster loading
            await context.route("**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2}", 
                              lambda route: route.abort())
            
            page = await context.new_page()
            
            # Track network requests and console logs
            tag_requests = []
            console_logs = []
            
            async def handle_request(request):
                if any(domain in request.url for domain in self.patterns.tag_domains):
                    tag_requests.append({
                        'url': request.url,
                        'timestamp': time.time(),
                        'resource_type': request.resource_type
                    })
            
            page.on('request', handle_request)
            page.on('console', lambda msg: console_logs.append(msg.text))
            
            try:
                # Navigate and wait for content
                await page.goto(url, wait_until='domcontentloaded', timeout=self.timeout * 1000)
                await page.wait_for_load_state('domcontentloaded')
                
                # Wait a bit for tags to load
                await page.wait_for_timeout(3000)
                
                final_dom = await page.content()
                
                return {
                    'network_requests': tag_requests,
                    'console_logs': console_logs,
                    'final_dom': final_dom
                }
            
            except Exception as e:
                print(f"JavaScript execution error: {str(e)}")
                return {
                    'network_requests': tag_requests,
                    'console_logs': console_logs,
                    'final_dom': ''
                }
            finally:
                await browser.close()
    
    def analyze_url(self, url: str) -> Dict[str, Any]:
        """Analyze a single URL for all tag types"""
        start_time = time.time()
        
        # Normalize URL
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        result = {
            'url': url,
            'status': 'success',
            'response_code': None,
            'load_time': 0,
            'javascript_executed': self.use_javascript,
            'detection_results': {},
            'warnings': [],
            'error': None
        }
        
        try:
            # Fetch static content
            response = requests.get(url, headers=self.get_headers(), timeout=self.timeout)
            result['response_code'] = response.status_code
            
            if response.status_code != 200:
                result['status'] = 'error'
                result['error'] = f'HTTP {response.status_code}'
                return result
            
            html_content = response.text
            scripts = self.extract_scripts(html_content)
            
            # Execute JavaScript if enabled
            if self.use_javascript:
                js_result = asyncio.run(self.execute_javascript(url))
                network_requests = js_result['network_requests']
            else:
                network_requests = []
            
            # Run all detections
            detectors = {
                'gtm': self.detect_gtm,
                'tealium': self.detect_tealium, 
                'gtag': self.detect_gtag,
                'meta_pixel': self.detect_meta_pixel,
                'tiktok_pixel': self.detect_tiktok_pixel,
                'linkedin_insight': self.detect_linkedin_insight,
                'snap_pixel': self.detect_snap_pixel,
                'universal_analytics': self.detect_universal_analytics
            }
            
            for name, detector in detectors.items():
                detection_result = detector(html_content, scripts, network_requests)
                result['detection_results'][name] = asdict(detection_result)
            
            # Add warnings
            if self.patterns.consent_managers.search(html_content):
                result['warnings'].append('Consent management detected - tags may load after user interaction')
            
            progressive_detected = any(
                result['detection_results'][name]['progressive_loading_detected'] 
                for name in detectors.keys()
            )
            if progressive_detected:
                result['warnings'].append('Progressive loading detected - some tags may load dynamically')
            
            result['load_time'] = round(time.time() - start_time, 2)
            
        except Exception as e:
            result['status'] = 'error'
            result['error'] = str(e)[:200]
            result['load_time'] = round(time.time() - start_time, 2)
        
        return result

def main():
    """Main function for testing a single URL"""
    # Configuration
    test_url = input("Enter URL to analyze: ").strip()
    if not test_url:
        test_url = "https://en.gacmotorsaudi.com/checkoutnew/"
    
    # Initialize checker
    checker = SingleUrlTagChecker(use_javascript=True, timeout=20)
    
    print(f"\nAnalyzing URL: {test_url}")
    print(f"JavaScript execution: {'Enabled' if checker.use_javascript else 'Disabled'}")
    print("-" * 60)
    
    # Analyze URL
    result = checker.analyze_url(test_url)
    
    # Display results
    print(f"\nStatus: {result['status']}")
    print(f"Response Code: {result['response_code']}")
    print(f"Load Time: {result['load_time']}s")
    
    if result['status'] == 'success':
        print("\nTag Detection Results:")
        print("=" * 60)
        
        tag_names = {
            'gtm': 'Google Tag Manager',
            'tealium': 'Tealium',
            'gtag': 'Google Analytics 4 (gtag)',
            'meta_pixel': 'Meta Pixel',
            'tiktok_pixel': 'TikTok Pixel',
            'linkedin_insight': 'LinkedIn Insight Tag',
            'snap_pixel': 'Snap Pixel',
            'universal_analytics': 'Universal Analytics'
        }
        
        for tag_key, tag_name in tag_names.items():
            detection = result['detection_results'].get(tag_key, {})
            
            if detection.get('found', False):
                print(f"\n✓ {tag_name}: DETECTED")
                print(f"  Confidence Score: {detection.get('confidence_score', 0)}")
                
                if detection.get('identifiers'):
                    print(f"  Identifiers: {', '.join(detection['identifiers'])}")
                
                if detection.get('detection_methods'):
                    print(f"  Detection Methods: {', '.join(detection['detection_methods'])}")
                
                if detection.get('verification_checks'):
                    print(f"  Verification: {', '.join(detection['verification_checks'])}")
                
                if detection.get('loading_method') != 'unknown':
                    print(f"  Loading Method: {detection['loading_method']}")
            else:
                print(f"\n✗ {tag_name}: NOT DETECTED")
        
        # Display warnings
        if result['warnings']:
            print("\n" + "=" * 60)
            print("Warnings:")
            for warning in result['warnings']:
                print(f"  ⚠ {warning}")
    
    else:
        print(f"\nError: {result['error']}")
    
    # Export to JSON
    print("\n" + "=" * 60)
    export = input("\nExport results to JSON? (y/n): ").strip().lower()
    if export == 'y':
        filename = f"tag_detection_{int(time.time())}.json"
        with open(filename, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"Results exported to {filename}")

if __name__ == "__main__":
    main()