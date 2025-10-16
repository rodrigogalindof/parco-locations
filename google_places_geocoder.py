#!/usr/bin/env python3
"""
Script to geocode parking locations using Google Places API.
This script will add Dirección, Latitud, and Longitud columns to the parking data.
"""

import requests
import time
import re
import json
import random
from typing import Dict, List, Tuple, Optional
from tqdm import tqdm

class GooglePlacesGeocoder:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.places_text_search_url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
        self.places_details_url = "https://maps.googleapis.com/maps/api/place/details/json"
        self.delay = 0.1  # 10 requests per second (conservative for Google Places API)
        self.headers = {'User-Agent': 'Mozilla/5.0 (compatible; GooglePlacesGeocoder/1.0)'}
        
        # Exponential backoff configuration
        self.max_retries = 5
        self.base_delay = 1.0  # Base delay in seconds
        self.max_delay = 60.0  # Maximum delay in seconds
        self.backoff_multiplier = 2.0
        self.jitter = True  # Add random jitter to prevent thundering herd
    
    def calculate_backoff_delay(self, attempt: int) -> float:
        """
        Calculate exponential backoff delay with jitter.
        """
        delay = min(self.base_delay * (self.backoff_multiplier ** attempt), self.max_delay)
        
        if self.jitter:
            # Add random jitter (±25% of the delay)
            jitter_range = delay * 0.25
            delay += random.uniform(-jitter_range, jitter_range)
        
        return max(0, delay)
    
    def is_retryable_error(self, status_code: int, response_data: dict = None) -> bool:
        """
        Determine if an error is retryable based on status code and response.
        """
        # HTTP status codes that are retryable
        retryable_status_codes = {429, 500, 502, 503, 504}
        
        if status_code in retryable_status_codes:
            return True
        
        # Google Places API specific error handling
        if response_data:
            status = response_data.get('status', '')
            error_message = response_data.get('error_message', '')
            
            # Rate limit exceeded
            if status == 'OVER_QUERY_LIMIT':
                return True
            
            # Server errors
            if status in ['UNKNOWN_ERROR', 'REQUEST_DENIED'] and 'quota' in error_message.lower():
                return True
        
        return False
    
    def make_api_request_with_retry(self, url: str, params: dict, max_retries: int = None) -> dict:
        """
        Make API request with exponential backoff retry logic.
        """
        if max_retries is None:
            max_retries = self.max_retries
        
        for attempt in range(max_retries + 1):
            try:
                response = requests.get(url, params=params, headers=self.headers, timeout=30)
                
                # Check for successful response
                if response.status_code == 200:
                    data = response.json()
                    
                    # Check for API-level errors
                    if data.get('status') == 'OK':
                        return data
                    elif self.is_retryable_error(200, data) and attempt < max_retries:
                        # API returned an error but it's retryable
                        delay = self.calculate_backoff_delay(attempt)
                        time.sleep(delay)
                        continue
                    else:
                        # Non-retryable API error
                        return data
                
                # Check for HTTP errors
                elif self.is_retryable_error(response.status_code) and attempt < max_retries:
                    delay = self.calculate_backoff_delay(attempt)
                    time.sleep(delay)
                    continue
                else:
                    # Non-retryable HTTP error
                    return {'status': 'ERROR', 'error_message': f'HTTP {response.status_code}'}
                    
            except requests.exceptions.Timeout:
                if attempt < max_retries:
                    delay = self.calculate_backoff_delay(attempt)
                    time.sleep(delay)
                    continue
                else:
                    return {'status': 'ERROR', 'error_message': 'Request timeout'}
                    
            except requests.exceptions.ConnectionError:
                if attempt < max_retries:
                    delay = self.calculate_backoff_delay(attempt)
                    time.sleep(delay)
                    continue
                else:
                    return {'status': 'ERROR', 'error_message': 'Connection error'}
                    
            except requests.exceptions.RequestException as e:
                if attempt < max_retries:
                    delay = self.calculate_backoff_delay(attempt)
                    time.sleep(delay)
                    continue
                else:
                    return {'status': 'ERROR', 'error_message': f'Request error: {str(e)}'}
                    
            except Exception as e:
                return {'status': 'ERROR', 'error_message': f'Unexpected error: {str(e)}'}
        
        return {'status': 'ERROR', 'error_message': 'Max retries exceeded'}
        
    def search_place(self, location_name: str, state: str, country: str = "Mexico") -> Dict:
        """
        Search for a place using Google Places API Text Search.
        
        Returns:
            Dictionary with all available place information
        """
        # Clean state name (remove parenthetical info)
        clean_state = state.split('(')[0].strip()
        
        # Try multiple search strategies
        search_queries = [
            f"{location_name} {clean_state} Mexico",
            f"{location_name} {clean_state}",
            f"{location_name} Mexico",
            f"{location_name}"  # Broader search
        ]
        
        for query in search_queries:
            params = {
                'query': query,
                'key': self.api_key,
                'region': 'mx',  # Bias results to Mexico
                'language': 'es'  # Spanish results
            }
            
            # Use robust API request with retry logic
            data = self.make_api_request_with_retry(self.places_text_search_url, params)
            
            
            if data.get('status') == 'OK' and data.get('results'):
                # Get the best result
                result = data['results'][0]
                
                # Get detailed information
                place_id = result.get('place_id')
                if place_id:
                    details = self.get_place_details(place_id)
                    if details.get('address'):
                        return details
                
                # Fallback to basic result data
                basic_details = {
                    'address': result.get('formatted_address', ''),
                    'latitude': result.get('geometry', {}).get('location', {}).get('lat'),
                    'longitude': result.get('geometry', {}).get('location', {}).get('lng'),
                    'place_id': result.get('place_id', ''),
                    'google_name': result.get('name', ''),
                    'types': ', '.join(result.get('types', [])),
                    'rating': result.get('rating'),
                    'user_ratings_total': result.get('user_ratings_total'),
                    'price_level': result.get('price_level'),
                    'website': '',
                    'phone': '',
                    'international_phone': '',
                    'opening_hours': []
                }
                
                if basic_details['latitude'] and basic_details['longitude']:
                    return basic_details
                    
            elif data.get('status') == 'ZERO_RESULTS':
                continue  # Try next query
            elif data.get('status') == 'ERROR':
                # Log error but continue with next query
                continue
        
        return {}
    
    def get_place_details(self, place_id: str) -> Dict:
        """
        Get detailed information about a place using its place_id.
        """
        params = {
            'place_id': place_id,
            'key': self.api_key,
            'fields': 'formatted_address,geometry,name,place_id,types,rating,user_ratings_total,price_level,opening_hours,website,formatted_phone_number,international_phone_number,photos',
            'language': 'es'
        }
        
        # Use robust API request with retry logic
        data = self.make_api_request_with_retry(self.places_details_url, params)
        
        if data.get('status') == 'OK' and data.get('result'):
            result = data['result']
            
            # Extract all available information
            details = {
                'address': result.get('formatted_address', ''),
                'latitude': result.get('geometry', {}).get('location', {}).get('lat'),
                'longitude': result.get('geometry', {}).get('location', {}).get('lng'),
                'place_id': result.get('place_id', ''),
                'google_name': result.get('name', ''),
                'types': ', '.join(result.get('types', [])),
                'rating': result.get('rating'),
                'user_ratings_total': result.get('user_ratings_total'),
                'price_level': result.get('price_level'),
                'website': result.get('website', ''),
                'phone': result.get('formatted_phone_number', ''),
                'international_phone': result.get('international_phone_number', ''),
                'opening_hours': result.get('opening_hours', {}).get('weekday_text', []),
                'photos': self.process_photos(result.get('photos', []))
            }
            
            return details
        
        return {}
    
    def process_parking_options(self, parking_options: List[Dict]) -> Dict:
        """
        Process parking options and create a summary.
        """
        if not parking_options:
            return {
                'parking_summary': 'No parking info',
                'free_parking_lot': False,
                'paid_parking_lot': False,
                'free_street_parking': False,
                'paid_street_parking': False,
                'valet_parking': False,
                'free_garage_parking': False,
                'paid_garage_parking': False
            }
        
        parking_types = []
        parking_details = {
            'free_parking_lot': False,
            'paid_parking_lot': False,
            'free_street_parking': False,
            'paid_street_parking': False,
            'valet_parking': False,
            'free_garage_parking': False,
            'paid_garage_parking': False
        }
        
        for option in parking_options:
            option_type = option.get('type', '')
            if option_type:
                parking_details[option_type] = True
                
                # Create human-readable summary
                if option_type == 'free_parking_lot':
                    parking_types.append('Estacionamiento gratuito')
                elif option_type == 'paid_parking_lot':
                    parking_types.append('Estacionamiento de pago')
                elif option_type == 'free_street_parking':
                    parking_types.append('Estacionamiento en calle gratuito')
                elif option_type == 'paid_street_parking':
                    parking_types.append('Estacionamiento en calle de pago')
                elif option_type == 'valet_parking':
                    parking_types.append('Valet parking')
                elif option_type == 'free_garage_parking':
                    parking_types.append('Estacionamiento en garaje gratuito')
                elif option_type == 'paid_garage_parking':
                    parking_types.append('Estacionamiento en garaje de pago')
        
        parking_summary = ', '.join(parking_types) if parking_types else 'No parking info'
        
        parking_details['parking_summary'] = parking_summary
        return parking_details
    
    def process_photos(self, photos: List[Dict]) -> Dict:
        """
        Process photo references and create URLs for different sizes.
        """
        if not photos:
            return {
                'photo_urls': [],
                'main_photo_url': None,
                'thumbnail_url': None
            }
        
        photo_urls = []
        main_photo_url = None
        thumbnail_url = None
        
        for i, photo in enumerate(photos[:3]):  # Limit to first 3 photos
            photo_reference = photo.get('photo_reference')
            if photo_reference:
                # Create URLs for different sizes
                max_width = 1200  # High quality
                thumbnail_width = 300  # Thumbnail
                
                photo_url = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth={max_width}&photo_reference={photo_reference}&key={self.api_key}"
                thumb_url = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth={thumbnail_width}&photo_reference={photo_reference}&key={self.api_key}"
                
                photo_urls.append(photo_url)
                
                if i == 0:  # First photo is main photo
                    main_photo_url = photo_url
                    thumbnail_url = thumb_url
        
        return {
            'photo_urls': photo_urls,
            'main_photo_url': main_photo_url,
            'thumbnail_url': thumbnail_url
        }
    
    def parse_markdown_file(self, file_path: str) -> List[Dict]:
        """
        Parse the markdown file and extract parking locations.
        """
        parking_data = []
        
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Split by state sections
        state_sections = re.split(r'^## (.+)$', content, flags=re.MULTILINE)
        
        for i in range(1, len(state_sections), 2):
            if i + 1 < len(state_sections):
                state_name = state_sections[i].strip()
                state_content = state_sections[i + 1]
                
                # Skip summary section
                if "Resumen por Tipo" in state_name:
                    break
                
                # Extract table rows (single pipe format)
                table_rows = re.findall(r'^\| (.+?) \| (.+?) \|$', state_content, re.MULTILINE)
                
                for row in table_rows:
                    parking_name = row[0].strip()
                    parking_type = row[1].strip()
                    
                    # Skip header row and separator rows
                    if parking_name.lower() in ['estacionamiento', 'tipo', 'dirección', 'latitud', 'longitud'] or '---' in parking_name:
                        continue
                    
                    parking_data.append({
                        'state': state_name,
                        'name': parking_name,
                        'type': parking_type,
                        'address': None,
                        'latitude': None,
                        'longitude': None,
                        'place_id': None,
                        'google_name': None,
                        'types': None,
                        'rating': None,
                        'user_ratings_total': None,
                        'price_level': None,
                        'website': None,
                        'phone': None,
                        'international_phone': None,
                        'opening_hours': None,
                        'photos': None,
                        'main_photo_url': None,
                        'thumbnail_url': None
                    })
        
        return parking_data
    
    def geocode_all_locations(self, parking_data: List[Dict]) -> List[Dict]:
        """
        Geocode all parking locations with rate limiting, progress bar, and error tracking.
        """
        found_count = 0
        error_count = 0
        retry_count = 0
        
        # Use tqdm for progress bar
        with tqdm(total=len(parking_data), desc="Processing locations", unit="loc") as pbar:
            for i, location in enumerate(parking_data):
                max_location_retries = 3
                location_success = False
                
                for location_attempt in range(max_location_retries):
                    try:
                        place_details = self.search_place(
                            location['name'], 
                            location['state']
                        )
                        
                        
                        # Update location with all available details
                        if place_details and place_details.get('address'):
                            location.update(place_details)
                            
                            # Extract photo URLs for easier access
                            if place_details.get('photos'):
                                location['main_photo_url'] = place_details['photos'].get('main_photo_url')
                                location['thumbnail_url'] = place_details['photos'].get('thumbnail_url')
                            
                            found_count += 1
                            location_success = True
                            break
                        else:
                            # No results found, but not an error
                            location_success = True
                            break
                            
                    except Exception as e:
                        if location_attempt < max_location_retries - 1:
                            # Retry this location
                            retry_count += 1
                            delay = self.calculate_backoff_delay(location_attempt)
                            time.sleep(delay)
                            continue
                        else:
                            # Max retries exceeded for this location
                            error_count += 1
                            location_success = True  # Mark as processed to continue
                            break
                
                # Rate limiting (only if we didn't already sleep for retry)
                if location_success:
                    time.sleep(self.delay)
                
                # Update progress bar
                pbar.update(1)
                
                # Update progress bar description with stats
                pbar.set_description(f"Processing locations (✅{found_count} ❌{error_count} 🔄{retry_count})")
        
        return parking_data
    
    def save_results(self, parking_data: List[Dict], output_file: str):
        """
        Save geocoded results to a JSON file for backup.
        """
        with open(output_file, 'w', encoding='utf-8') as file:
            json.dump(parking_data, file, ensure_ascii=False, indent=2)
    
    def save_geojson_for_mapbox(self, parking_data: List[Dict], output_file: str):
        """
        Save results in GeoJSON format ready for Mapbox upload.
        """
        geojson = {
            "type": "FeatureCollection",
            "features": []
        }
        
        for location in parking_data:
            # Only include locations with valid coordinates
            if location.get('latitude') and location.get('longitude'):
                feature = {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [location['longitude'], location['latitude']]
                    },
                    "properties": {
                        "name": location['name'],
                        "type": location['type'],
                        "state": location['state'],
                        "address": location.get('address', ''),
                        "google_name": location.get('google_name', ''),
                        "place_id": location.get('place_id', ''),
                        "rating": location.get('rating'),
                        "user_ratings_total": location.get('user_ratings_total'),
                        "price_level": location.get('price_level'),
                        "website": location.get('website', ''),
                        "phone": location.get('phone', ''),
                        "international_phone": location.get('international_phone', ''),
                        "opening_hours": location.get('opening_hours', []),
                        "main_photo_url": location.get('main_photo_url', ''),
                        "thumbnail_url": location.get('thumbnail_url', ''),
                        "types": location.get('types', '')
                    }
                }
                geojson["features"].append(feature)
        
        with open(output_file, 'w', encoding='utf-8') as file:
            json.dump(geojson, file, ensure_ascii=False, indent=2)
        
        print(f"GeoJSON file created for Mapbox: {output_file}")
        print(f"Total features: {len(geojson['features'])}")
    
    def create_sample_markdown_update(self, parking_data: List[Dict], output_file: str):
        """
        Create a sample markdown file showing how the updated table will look.
        """
        # Group by state
        state_data = {}
        for location in parking_data:
            state = location['state']
            if state not in state_data:
                state_data[state] = []
            state_data[state].append(location)
        
        with open(output_file, 'w', encoding='utf-8') as file:
            file.write("# Estacionamientos con Convenio Parco - Google Places API Sample\n\n")
            
            for state, locations in state_data.items():
                file.write(f"## {state}\n\n")
                
                # Create table with all columns
                file.write("| Estacionamiento | Tipo | Dirección | Latitud | Longitud | Google Name | Rating | Reviews | Price Level | Website | Phone | Main Photo |\n")
                file.write("|-----------------|------|-----------|---------|----------|-------------|--------|---------|-------------|---------|-------|------------|\n")
                
                for location in locations:
                    name = location['name']
                    type_name = location['type']
                    address = location['address'] or "No encontrada"
                    lat = location['latitude'] or "N/A"
                    lon = location['longitude'] or "N/A"
                    google_name = location['google_name'] or "N/A"
                    rating = location['rating'] or "N/A"
                    reviews = location['user_ratings_total'] or "N/A"
                    price_level = location['price_level'] or "N/A"
                    website = location['website'] or "N/A"
                    phone = location['phone'] or "N/A"
                    main_photo = location['main_photo_url'] or "N/A"
                    
                    # Truncate long fields for better table display
                    if len(address) > 40:
                        address = address[:37] + "..."
                    if len(google_name) > 20:
                        google_name = google_name[:17] + "..."
                    if len(website) > 20:
                        website = website[:17] + "..."
                    if len(phone) > 15:
                        phone = phone[:12] + "..."
                    if len(main_photo) > 30:
                        main_photo = main_photo[:27] + "..."
                    
                    file.write(f"| {name} | {type_name} | {address} | {lat} | {lon} | {google_name} | {rating} | {reviews} | {price_level} | {website} | {phone} | {main_photo} |\n")
                
                file.write("\n")
        
        print(f"Sample markdown created: {output_file}")
    
    def update_markdown_file(self, file_path: str, parking_data: List[Dict]):
        """
        Update the original markdown file with the new columns.
        """
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Group data by state
        state_data = {}
        for location in parking_data:
            state = location['state']
            if state not in state_data:
                state_data[state] = []
            state_data[state].append(location)
        
        # Update each state section
        for state, locations in state_data.items():
            # Find the state section
            state_pattern = rf'^## {re.escape(state)}$'
            state_match = re.search(state_pattern, content, re.MULTILINE)
            
            if state_match:
                # Find the table in this section
                start_pos = state_match.end()
                next_section = re.search(r'^## ', content[start_pos:], re.MULTILINE)
                end_pos = start_pos + next_section.start() if next_section else len(content)
                
                state_section = content[start_pos:end_pos]
                
                # Create new table
                new_table = "| Estacionamiento | Tipo | Dirección | Latitud | Longitud | Google Name | Rating | Reviews | Price Level | Website | Phone | Main Photo |\n"
                new_table += "|-----------------|------|-----------|---------|----------|-------------|--------|---------|-------------|---------|-------|------------|\n"
                
                for location in locations:
                    name = location['name']
                    type_name = location['type']
                    address = location['address'] or "No encontrada"
                    lat = location['latitude'] or "N/A"
                    lon = location['longitude'] or "N/A"
                    google_name = location['google_name'] or "N/A"
                    rating = location['rating'] or "N/A"
                    reviews = location['user_ratings_total'] or "N/A"
                    price_level = location['price_level'] or "N/A"
                    website = location['website'] or "N/A"
                    phone = location['phone'] or "N/A"
                    main_photo = location['main_photo_url'] or "N/A"
                    
                    # Truncate long fields for better table display
                    if len(address) > 40:
                        address = address[:37] + "..."
                    if len(google_name) > 20:
                        google_name = google_name[:17] + "..."
                    if len(website) > 20:
                        website = website[:17] + "..."
                    if len(phone) > 15:
                        phone = phone[:12] + "..."
                    if len(main_photo) > 30:
                        main_photo = main_photo[:27] + "..."
                    
                    new_table += f"| {name} | {type_name} | {address} | {lat} | {lon} | {google_name} | {rating} | {reviews} | {price_level} | {website} | {phone} | {main_photo} |\n"
                
                # Replace the old table with the new one
                table_pattern = r'\| Estacionamiento \| Tipo \|.*?(?=\n\n|\Z)'
                new_state_section = re.sub(table_pattern, new_table.strip(), state_section, flags=re.DOTALL)
                
                content = content[:start_pos] + new_state_section + content[end_pos:]
        
        # Write updated content
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(content)

def main():
    # Read API key from file
    try:
        with open('api-key.md', 'r') as f:
            api_key = f.read().strip()
    except FileNotFoundError:
        print("Error: api-key.md file not found")
        return
    
    if not api_key:
        print("Error: API key is empty")
        return
    
    geocoder = GooglePlacesGeocoder(api_key)
    
    # Parse the markdown file
    parking_data = geocoder.parse_markdown_file('estacionamientos-parco.md')
    
    # Process all locations for full deployment with robust error handling
    geocoded_data = geocoder.geocode_all_locations(parking_data)
    
    # Save results
    geocoder.save_results(geocoded_data, 'google_places_results_full.json')
    
    # Save GeoJSON for Mapbox (as .json file)
    geocoder.save_geojson_for_mapbox(geocoded_data, 'parking_locations_mapbox.json')
    
    # Update the original markdown file
    geocoder.update_markdown_file('estacionamientos-parco.md', geocoded_data)
    
    # Show final deployment results
    print("\n🎉 FULL DEPLOYMENT COMPLETED!")
    found_locations = [loc for loc in geocoded_data if loc['address']]
    not_found_locations = [loc for loc in geocoded_data if not loc['address']]
    
    success_rate = len(found_locations)/len(geocoded_data)*100
    print(f"✅ Successfully processed: {len(found_locations)}/{len(geocoded_data)} locations ({success_rate:.1f}%)")
    print(f"❌ Not found: {len(not_found_locations)} locations")
    
    if success_rate < 90:
        print(f"⚠️  Warning: Success rate is below 90%. Consider checking API quota or network connectivity.")
    
    # Show summary by state
    state_summary = {}
    for location in found_locations:
        state = location['state']
        if state not in state_summary:
            state_summary[state] = 0
        state_summary[state] += 1
    
    print(f"\n📊 Results by State:")
    for state, count in sorted(state_summary.items()):
        print(f"  • {state}: {count} locations")
    
    if not_found_locations:
        print(f"\n❓ Locations not found:")
        for location in not_found_locations[:10]:  # Show first 10
            print(f"  • {location['name']} ({location['state']})")
        if len(not_found_locations) > 10:
            print(f"  ... and {len(not_found_locations) - 10} more")
    
    print(f"\n💾 Files created:")
    print(f"  • Backup: estacionamientos-parco-backup-*.md")
    print(f"  • Full results: google_places_results_full.json")
    print(f"  • Mapbox JSON: parking_locations_mapbox.json")
    print(f"  • Updated: estacionamientos-parco.md")
    
    print(f"\n🚀 Your parking locations database is now enhanced with:")
    print(f"  • Complete addresses and coordinates")
    print(f"  • Google ratings and reviews")
    print(f"  • High-quality photos")
    print(f"  • Contact information (websites, phones)")
    print(f"  • Official Google business names")

if __name__ == "__main__":
    main()
