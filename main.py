import requests
from requests.structures import CaseInsensitiveDict
import json
from datetime import datetime, timezone
import geopandas as gpd
from shapely.geometry import Point
import streamlit as st
import pandas as pd
import plotly.express as px


@st.cache_data
def load_shapefiles():
    countries = gpd.read_file("shapefiles\ne_10m_admin_0_countries.shp")
    states = gpd.read_file("shapefiles\ne_10m_admin_1_states_provinces.shp")
    return countries, states

countries, states = load_shapefiles()

BASE_URL = "https://a.windbornesystems.com/treasure/{:02d}.json"

def fetch_snapshot(hour_offset: int):
    """Download a single hour snapshot."""
    url = BASE_URL.format(hour_offset)
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[ERROR] Failed to fetch {url}: {e}")
        return None


def parse_snapshot(raw):
    """
    Extract flight updates from a snapshot.
    The API is undocumented, so we defensively extract anything that looks like:
        { "lat": ..., "lon": ..., "alt": ..., "id": ... }
    """
    if raw is None:
        return []

    results = []

    # Case 1: JSON is a list
    if isinstance(raw, list):
        for item in raw:
            parsed = parse_flight_record(item)
            if parsed:
                results.append(parsed)
        return results

    # Case 2: JSON is a dict
    if isinstance(raw, dict):
        # Might contain nested lists
        for key, value in raw.items():
            if isinstance(value, list):
                for item in value:
                    parsed = parse_flight_record(item)
                    if parsed:
                        results.append(parsed)
        return results

    print(f"[WARN] Unknown JSON structure: {type(raw)}")
    return []


def parse_flight_record(obj):
    """
    Extract a single flight record from an object.
    We don't know the schema, so we look for the fields we care about.
    """
    
    lat = obj[0]
    lon = obj[1]
    alt = obj[2]

    point = Point(lon, lat)

    country_point = countries[countries.contains(point)]
    state_point = states[states.contains(point)]

    country = country_point["NAME"].values[0] if not country_point.empty else None
    state = state_point["name"].values[0] if not state_point.empty else None

    if lat is None or lon is None:
        return None  # can't use without position

    return {
        "lat": lat,
        "lon": lon,
        "alt": alt,
        "country": country,
        "state": state,
    }


def collect_flight_history(hours=24):
    """Fetches and parses the last N hours of snapshots."""
    all_records = []

    for h in range(hours):
        raw = fetch_snapshot(h)
        entries = parse_snapshot(raw)
        print(f"[INFO] Hour {h}: extracted {len(entries)} entries")
        all_records.extend(entries)

    return all_records

if st.button("Refresh Data"):
    records = collect_flight_history(24)

st.set_page_config(layout="wide")
st.title("🌍 Live Balloon Constellation Tracker")

with st.spinner("Fetching last 24h of balloon data..."):
    records = collect_flight_history(24)

# Convert to DataFrame
df = pd.DataFrame(records)

# Show interactive map
st.subheader("Balloon Positions Map")
fig = px.scatter_geo(
    df,
    lat="lat",
    lon="lon",
    hover_name="country",
    hover_data=["state", "alt"],
    color="country",
    scope="world",
    title="Live Balloon Constellation"
)
st.plotly_chart(fig, use_container_width=True)

# Show raw data
st.subheader("Balloon Data Table")
st.dataframe(df)

# Summary chart
st.subheader("Balloon Count by Country")
country_counts = df["country"].value_counts().reset_index()
country_counts.columns = ["country", "balloon_count"]
st.bar_chart(country_counts.set_index("country"))
