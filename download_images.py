#!/usr/bin/env python3
"""
Script to download Google Places images locally and organize them properly.
This script will:
1. Read the JSON data file
2. Download all Google Places images to a local folder
3. Update the JSON data to reference local image paths
4. Ensure no API keys are exposed in the final output
"""

import json
import os
import requests
import time
from urllib.parse import urlparse, parse_qs
import hashlib
from pathlib import Path

# Configuration
API_KEY = "AIzaSyA22DVhZXNaUCRzBREm7WZOOUMbgMTir3c"
JSON_FILE = "google_places_results_full.json"
IMAGES_FOLDER = "Parking Images"
OUTPUT_JSON = "google_places_results_with_local_images.json"

def sanitize_filename(name):
    """Create a safe filename from a place name"""
    # Remove or replace invalid characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        name = name.replace(char, '_')
    
    # Limit length and remove extra spaces
    name = name.strip()[:100]
    return name

def get_photo_reference_from_url(url):
    """Extract photo_reference from Google Places photo URL"""
    if 'photo_reference=' in url:
        return url.split('photo_reference=')[1].split('&')[0]
    return None

def download_image(url, filepath, max_retries=3):
    """Download an image from URL to filepath"""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            print(f"✓ Downloaded: {os.path.basename(filepath)}")
            return True
            
        except Exception as e:
            print(f"✗ Attempt {attempt + 1} failed for {os.path.basename(filepath)}: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)  # Wait before retry
    
    return False

def process_place_images(place, images_folder, api_key):
    """Process all images for a single place"""
    place_name = sanitize_filename(place['name'])
    place_id = place.get('place_id', '')
    
    # Create a unique identifier for this place
    place_identifier = f"{place_name}_{place_id[:8]}"
    
    updated_place = place.copy()
    downloaded_images = []
    
    # Process main photo
    if place.get('main_photo_url'):
        photo_ref = get_photo_reference_from_url(place['main_photo_url'])
        if photo_ref:
            # Add API key to URL for downloading
            download_url = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=1200&photo_reference={photo_ref}&key={api_key}"
            filename = f"{place_identifier}_main.jpg"
            filepath = os.path.join(images_folder, filename)
            
            if download_image(download_url, filepath):
                # Update the URL to point to local file
                updated_place['main_photo_url'] = f"Parking Images/{filename}"
                downloaded_images.append(filename)
    
    # Process thumbnail
    if place.get('thumbnail_url'):
        photo_ref = get_photo_reference_from_url(place['thumbnail_url'])
        if photo_ref:
            download_url = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=300&photo_reference={photo_ref}&key={api_key}"
            filename = f"{place_identifier}_thumb.jpg"
            filepath = os.path.join(images_folder, filename)
            
            if download_image(download_url, filepath):
                updated_place['thumbnail_url'] = f"Parking Images/{filename}"
                downloaded_images.append(filename)
    
    # Process photos array
    if place.get('photos', {}).get('photo_urls'):
        updated_photos = []
        for i, photo_url in enumerate(place['photos']['photo_urls']):
            photo_ref = get_photo_reference_from_url(photo_url)
            if photo_ref:
                download_url = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=1200&photo_reference={photo_ref}&key={api_key}"
                filename = f"{place_identifier}_photo_{i+1}.jpg"
                filepath = os.path.join(images_folder, filename)
                
                if download_image(download_url, filepath):
                    updated_photos.append(f"Parking Images/{filename}")
                    downloaded_images.append(filename)
        
        if updated_photos:
            updated_place['photos']['photo_urls'] = updated_photos
    
    # Update main_photo_url and thumbnail_url in photos object if they exist
    if 'photos' in updated_place:
        if updated_place.get('main_photo_url'):
            updated_place['photos']['main_photo_url'] = updated_place['main_photo_url']
        if updated_place.get('thumbnail_url'):
            updated_place['photos']['thumbnail_url'] = updated_place['thumbnail_url']
    
    return updated_place, downloaded_images

def main():
    print("🚀 Starting image download process...")
    
    # Create images folder
    os.makedirs(IMAGES_FOLDER, exist_ok=True)
    print(f"📁 Created folder: {IMAGES_FOLDER}")
    
    # Load JSON data
    print(f"📖 Loading data from {JSON_FILE}...")
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        places_data = json.load(f)
    
    print(f"📍 Found {len(places_data)} places to process")
    
    # Process each place
    updated_places = []
    total_downloaded = 0
    places_with_images = 0
    
    for i, place in enumerate(places_data):
        print(f"\n[{i+1}/{len(places_data)}] Processing: {place['name']}")
        
        updated_place, downloaded_images = process_place_images(place, IMAGES_FOLDER, API_KEY)
        updated_places.append(updated_place)
        
        if downloaded_images:
            places_with_images += 1
            total_downloaded += len(downloaded_images)
            print(f"   Downloaded {len(downloaded_images)} images")
        else:
            print(f"   No images found or downloaded")
        
        # Small delay to be respectful to the API
        time.sleep(0.1)
    
    # Save updated JSON data
    print(f"\n💾 Saving updated data to {OUTPUT_JSON}...")
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(updated_places, f, ensure_ascii=False, indent=2)
    
    # Summary
    print(f"\n✅ Download complete!")
    print(f"   📊 Places processed: {len(places_data)}")
    print(f"   🖼️  Places with images: {places_with_images}")
    print(f"   📸 Total images downloaded: {total_downloaded}")
    print(f"   📁 Images saved to: {IMAGES_FOLDER}/")
    print(f"   📄 Updated JSON saved to: {OUTPUT_JSON}")
    
    # Verify no API keys in output
    print(f"\n🔍 Verifying no API keys in output...")
    with open(OUTPUT_JSON, 'r') as f:
        content = f.read()
        if API_KEY in content:
            print(f"❌ WARNING: API key found in output file!")
        else:
            print(f"✅ No API keys found in output file")

if __name__ == "__main__":
    main()
