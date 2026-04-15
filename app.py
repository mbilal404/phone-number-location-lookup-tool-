from flask import Flask, render_template, request, jsonify
import os
import phonenumbers
from phonenumbers import geocoder, carrier, timezone
from geopy.geocoders import Nominatim
import requests as http_requests
import secrets
import time

import share_store

app = Flask(__name__)

# Set PUBLIC_BASE_URL=http://192.168.1.5:8080 so share links work on other phones on your Wi‑Fi
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")

geolocator = Nominatim(user_agent="phone-tracker-hackathon")

PK_LANDLINE_CODES = {
    "21": "Karachi", "22": "Hyderabad", "23": "Larkana",
    "24": "Sukkur", "25": "Nawabshah",
    "41": "Faisalabad", "42": "Lahore", "44": "Okara",
    "46": "Sahiwal", "47": "Gujranwala", "48": "Sargodha",
    "51": "Islamabad", "52": "Sialkot", "53": "Jhelum",
    "54": "Gujrat", "55": "Mandi Bahauddin", "56": "Attock",
    "57": "Abbottabad",
    "61": "Multan", "62": "Bahawalpur", "63": "Rahim Yar Khan",
    "64": "D.G. Khan", "65": "Vehari", "66": "Muzaffargarh",
    "67": "Khanewal", "68": "Bahawalnagar",
    "71": "Sukkur", "74": "Mirpur Khas",
    "81": "Quetta", "82": "Khuzdar",
    "91": "Peshawar", "92": "Mardan", "93": "Bannu",
    "94": "Swat", "95": "Dir",
    "992": "Mansehra", "995": "Chitral", "997": "Buner",
}

CARRIER_FULL_NAMES = {
    "Jazz": "Jazz (Mobilink)",
    "Zong": "Zong (CMPak)",
    "Ufone": "Ufone (PTML)",
    "Telenor": "Telenor Pakistan",
    "Warid": "Jazz (formerly Warid)",
}


def get_pk_landline_city(national_number_str):
    num = national_number_str.lstrip("0")
    for code_len in (3, 2):
        code = num[:code_len]
        if code in PK_LANDLINE_CODES:
            return PK_LANDLINE_CODES[code]
    return None


def fetch_ip_location(client_ip=None):
    """Get location from IP using ip-api.com (free, no key)."""
    try:
        if client_ip and client_ip not in ("127.0.0.1", "::1", "localhost"):
            url = f"http://ip-api.com/json/{client_ip}?fields=status,country,regionName,city,lat,lon,isp"
        else:
            url = "http://ip-api.com/json/?fields=status,country,regionName,city,lat,lon,isp"
        resp = http_requests.get(url, timeout=4)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "success":
                return {
                    "city": data.get("city"),
                    "region": data.get("regionName"),
                    "country": data.get("country"),
                    "lat": data.get("lat"),
                    "lon": data.get("lon"),
                    "isp": data.get("isp"),
                }
    except Exception:
        pass
    return None


def geocode_location(query):
    """Geocode a location string to lat/lng."""
    try:
        result = geolocator.geocode(query)
        if result:
            return result.latitude, result.longitude
    except Exception:
        pass
    return None, None


def lookup_phone(phone_number_str, client_ip=None):
    try:
        parsed = phonenumbers.parse(phone_number_str)
    except phonenumbers.NumberParseException:
        return {"error": "Invalid phone number format. Use international format like +923001234567"}

    if not phonenumbers.is_valid_number(parsed):
        if not phonenumbers.is_possible_number(parsed):
            return {"error": "This is not a valid phone number."}

    location = geocoder.description_for_number(parsed, "en") or "Unknown"
    carrier_name = carrier.name_for_number(parsed, "en") or "Unknown"
    number_type = phonenumbers.number_type(parsed)

    type_map = {
        phonenumbers.PhoneNumberType.MOBILE: "Mobile",
        phonenumbers.PhoneNumberType.FIXED_LINE: "Fixed Line",
        phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE: "Fixed Line or Mobile",
        phonenumbers.PhoneNumberType.TOLL_FREE: "Toll Free",
        phonenumbers.PhoneNumberType.PREMIUM_RATE: "Premium Rate",
        phonenumbers.PhoneNumberType.VOIP: "VoIP",
        phonenumbers.PhoneNumberType.PERSONAL_NUMBER: "Personal",
        phonenumbers.PhoneNumberType.UNKNOWN: "Unknown",
    }
    type_label = type_map.get(number_type, "Unknown")

    tz_list = timezone.time_zones_for_number(parsed)
    tz_str = ", ".join(tz_list) if tz_list else "Unknown"

    country_code = phonenumbers.region_code_for_number(parsed)
    formatted_intl = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
    formatted_national = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.NATIONAL)
    carrier_display = CARRIER_FULL_NAMES.get(carrier_name, carrier_name)
    national_str = str(parsed.national_number)

    city = None
    accuracy = "country"
    zoom_level = 6
    location_method = "number_db"

    # Step 1: Landline area codes (100% accurate for city)
    if country_code == "PK" and type_label == "Fixed Line":
        city = get_pk_landline_city(national_str)
        if city:
            accuracy = "city"
            location = f"{city}, Pakistan"
            zoom_level = 13

    # Step 2: phonenumbers library city-level (US/UK etc)
    if location and "," in location and location != "Unknown":
        accuracy = "city"
        zoom_level = 13

    # Step 3: Geocode the determined location
    lat, lng = None, None
    if accuracy == "city":
        lat, lng = geocode_location(location)

    # Step 4: If still country-level only, use IP geolocation to get a better pin
    if accuracy == "country":
        ip_data = fetch_ip_location(client_ip)
        if ip_data and ip_data.get("lat") and ip_data.get("lon"):
            lat = ip_data["lat"]
            lng = ip_data["lon"]
            ip_city = ip_data.get("city", "")
            ip_region = ip_data.get("region", "")
            ip_country = ip_data.get("country", "")

            parts = [p for p in [ip_city, ip_region, ip_country] if p]
            location = ", ".join(parts) if parts else location

            accuracy = "ip_enhanced"
            location_method = "number_db + ip_geolocation"
            zoom_level = 12
            city = ip_city

    # Step 5: Final fallback - just geocode the country
    if lat is None and country_code:
        lat, lng = geocode_location(country_code)

    accuracy_labels = {
        "city": "City-level (verified from area code)",
        "ip_enhanced": "City-level (enhanced with IP geolocation)",
        "country": "Country-level only",
    }

    return {
        "formatted_international": formatted_intl,
        "formatted_national": formatted_national,
        "location": location,
        "carrier": carrier_display,
        "phone_type": type_label,
        "timezone": tz_str,
        "country_code": country_code or "Unknown",
        "latitude": lat,
        "longitude": lng,
        "is_valid": phonenumbers.is_valid_number(parsed),
        "accuracy": accuracy,
        "accuracy_label": accuracy_labels.get(accuracy, "Unknown"),
        "zoom_level": zoom_level,
        "city": city,
        "location_method": location_method,
    }


def _reverse_address(lat, lng):
    try:
        loc = geolocator.reverse((lat, lng), language="en", timeout=8)
        return loc.address if loc else None
    except Exception:
        return None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/share/<token>")
def share_page(token):
    if not share_store.get_session(token):
        return render_template("share_invalid.html"), 404
    return render_template("share.html", token=token)


@app.route("/api/share/create", methods=["POST"])
def share_create():
    """Create a unique link. When opened on the target phone, that browser can report GPS (with user consent)."""
    data = request.get_json() or {}
    phone = (data.get("phone") or "").strip()
    if not phone:
        return jsonify({"error": "Enter a phone number first (used as a label only)."}), 400
    if not phone.startswith("+"):
        phone = "+" + phone

    try:
        parsed = phonenumbers.parse(phone)
        if not phonenumbers.is_valid_number(parsed):
            return jsonify({"error": "Invalid phone number."}), 400
        label = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
    except phonenumbers.NumberParseException:
        return jsonify({"error": "Invalid phone number format."}), 400

    token = secrets.token_urlsafe(16)
    share_store.create_session(token, label)

    base = PUBLIC_BASE_URL or request.host_url.rstrip("/")
    share_url = f"{base}/share/{token}"
    return jsonify({
        "token": token,
        "share_url": share_url,
        "phone_label": label,
        "used_public_base_url": bool(PUBLIC_BASE_URL),
    })


@app.route("/api/share/<token>/report", methods=["POST"])
def share_report(token):
    """Called from the target phone after user allows GPS."""
    if not share_store.get_session(token):
        return jsonify({"error": "Invalid or expired link."}), 404

    data = request.get_json() or {}
    try:
        lat = float(data.get("latitude"))
        lng = float(data.get("longitude"))
    except (TypeError, ValueError):
        return jsonify({"error": "latitude and longitude required."}), 400

    acc = data.get("accuracy")
    try:
        accuracy_m = float(acc) if acc is not None else None
    except (TypeError, ValueError):
        accuracy_m = None

    address = _reverse_address(lat, lng)
    share_store.update_session_gps(token, lat, lng, accuracy_m, address)
    return jsonify({"ok": True, "address": address})


@app.route("/api/share/<token>/poll", methods=["GET"])
def share_poll(token):
    """Main dashboard polls this to show the phone's GPS once reported."""
    s = share_store.get_session(token)
    if not s:
        return jsonify({"error": "Invalid or expired link."}), 404

    return jsonify({
        "phone_label": s["phone_label"],
        "status": s["status"],
        "latitude": s["lat"],
        "longitude": s["lng"],
        "accuracy_m": s["accuracy_m"],
        "address": s["address"],
        "updated_at": s["updated_at"],
    })


@app.route("/api/lookup", methods=["POST"])
def api_lookup():
    data = request.get_json()
    phone = data.get("phone", "").strip()
    if not phone:
        return jsonify({"error": "Please enter a phone number."}), 400

    if not phone.startswith("+"):
        phone = "+" + phone

    # Get the real client IP (works behind proxies too)
    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    if client_ip and "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()

    result = lookup_phone(phone, client_ip)
    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)


@app.route("/api/ip-locate", methods=["GET"])
def ip_locate():
    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    if client_ip and "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()

    data = fetch_ip_location(client_ip)
    if data:
        return jsonify({
            "city": data.get("city"),
            "region": data.get("region"),
            "country": data.get("country"),
            "latitude": data.get("lat"),
            "longitude": data.get("lon"),
            "isp": data.get("isp"),
        })
    return jsonify({"error": "Could not determine IP location"}), 500


if __name__ == "__main__":
    if not PUBLIC_BASE_URL:
        print(
            "Tip: export PUBLIC_BASE_URL=http://YOUR_COMPUTER_LAN_IP:8080 "
            "so “Exact phone GPS” links work on other phones (not localhost)."
        )
    app.run(debug=True, port=8080, host="0.0.0.0")
