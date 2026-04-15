# PhoneTracer - Phone Number Location Tracker

A hackathon-ready web tool that looks up any international phone number and displays its registered region, carrier, and approximate location on an interactive dark-themed map.

## What It Does

- Parses international phone numbers and validates them
- Shows the registered **region**, **carrier**, **phone type**, and **timezone**
- Geocodes the region and displays it on a **Leaflet.js dark map** with a pulsing marker
- Stores recent searches in local storage for quick re-lookups

> **Note:** This tool shows the *registered region* of a phone number (based on its prefix/number plan), not real-time GPS tracking. Real-time tracking requires telecom-level access.

## Setup

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Run the app
python app.py

# 3. Open in browser
# Go to http://localhost:5000
```

## Usage

1. Enter any international phone number (e.g. `+92 300 1234567`)
2. Click **Track**
3. View phone details, location info, and the map

## Tech Stack

- **Backend:** Python, Flask, phonenumbers, geopy
- **Frontend:** HTML/CSS/JS, Leaflet.js (dark CARTO tiles)
- **Geocoding:** OpenStreetMap Nominatim (free, no API key needed)
