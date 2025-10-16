# Google Places API Setup Guide

## Step 1: Get Google Cloud Account
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Sign in with your Google account
3. Create a new project or select an existing one

## Step 2: Enable Places API
1. In the Google Cloud Console, go to "APIs & Services" > "Library"
2. Search for "Places API"
3. Click on "Places API" and then "Enable"

## Step 3: Create API Key
1. Go to "APIs & Services" > "Credentials"
2. Click "Create Credentials" > "API Key"
3. Copy your API key

## Step 4: Set Usage Limits (Recommended)
1. Click on your API key to edit it
2. Under "API restrictions", select "Restrict key"
3. Choose "Places API" from the list
4. Under "Application restrictions", you can set IP restrictions if needed

## Step 5: Pricing Information
- **Places API Text Search**: $32 per 1,000 requests
- **Places API Details**: $17 per 1,000 requests
- For 320 locations, estimated cost: ~$15-20 USD

## Step 6: Run the Script
```bash
python3 google_places_geocoder.py
```

Enter your API key when prompted.

## Alternative: Free Trial
Google Cloud offers $300 in free credits for new users, which should be more than enough for this project.
