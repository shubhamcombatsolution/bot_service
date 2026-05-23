# import googlemaps
# from .BaseTool import BaseTool

# class NearbyFacilitiesTool(BaseTool):
#     """
#     Tool to fetch nearby facilities such as schools, hospitals, and shopping centers.
#     """
#     def __init__(self, api_key: str = "<GOOGLE_MAPS_API_KEY>"):
#         super().__init__(
#             name="Nearby Facilities Tool",
#             description="Fetch nearby facilities for a given location and facility type."
#         )
#         try:
#             self.gmaps = googlemaps.Client(key=api_key)
#         except Exception as e:
#             raise ValueError(f"Error initializing Google Maps client: {str(e)}")

#     def process(self, location: str, facility_type: str):
#         """
#         Fetch nearby facilities based on the location and facility type.

#         Args:
#             location (str): Location name or coordinates (e.g., "New York" or "19.0760,72.8777").
#             facility_type (str): Type of facility (e.g., "school", "hospital").

#         Returns:
#             list: List of facilities with details such as name, address, rating, and distance.
#         """
#         try:
#             # Fetch nearby places based on facility type
#             query = f"{facility_type} near {location}"
#             places = self.gmaps.places(query=query)

#             if 'results' not in places or not places["results"]:
#                 return f"No {facility_type} found near '{location}'."

#             places_details = []
#             for place in places["results"]:
#                 place_name = place.get("name", "Unknown")
#                 place_address = place.get("formatted_address", "Unknown")
#                 place_rating = place.get("rating", "N/A")

#                 # Extract latitude & longitude for distance calculation
#                 place_location = place.get("geometry", {}).get("location", {})
#                 place_lat = place_location.get("lat")
#                 place_lng = place_location.get("lng")

#                 if place_lat and place_lng:
#                     # Use distance matrix API to calculate distance
#                     distance_result = self.gmaps.distance_matrix(
#                         origins=[location],  # Directly using location instead of geocoding
#                         destinations=[(place_lat, place_lng)],
#                         mode="driving"
#                     )

#                     distance = distance_result["rows"][0]["elements"][0].get("distance", {}).get("text", "N/A")
#                 else:
#                     distance = "Unknown"

#                 # Append facility details
#                 places_details.append({
#                     "name": place_name,
#                     "address": place_address,
#                     "rating": place_rating,
#                     "distance_from_location": distance
#                 })

#             return places_details
#         except Exception as e:
#             return f"Error fetching facilities: {e}"

# Tools/NearbyFacilitiesTool.py

# import os
# import googlemaps
# from dotenv import load_dotenv

# load_dotenv()

# class NearbyFacilitiesTool:
#     def __init__(self, api_key=None):
#         # Load from .env if not provided
#         self.api_key = api_key or os.getenv("GOOGLE_MAPS_API_KEY")
#         if not self.api_key:
#             raise ValueError("Google Maps API key is required. Provide api_key or set GOOGLE_MAPS_API_KEY in .env")
        
#         self.gmaps = googlemaps.Client(key=self.api_key)

#     def process(self, location, facility_type, radius=2000):
#         """
#         Find nearby facilities (schools, hospitals, etc.).
        
#         Args:
#             location (str): Address or place name (will be geocoded).
#             facility_type (str): e.g. 'hospital', 'school', 'restaurant'
#             radius (int): Search radius in meters (default: 2000m)

#         Returns:
#             list of dicts: Nearby facility info
#         """
#         # Convert location into lat/lng
#         geocode_result = self.gmaps.geocode(location)
#         if not geocode_result:
#             return {"error": f"Could not geocode location: {location}"}
        
#         latlng = geocode_result[0]["geometry"]["location"]

#         # Search nearby places
#         places = self.gmaps.places_nearby(
#             location=(latlng["lat"], latlng["lng"]),
#             radius=radius,
#             type=facility_type
#         )

#         results = []
#         for place in places.get("results", []):
#             results.append({
#                 "name": place.get("name"),
#                 "address": place.get("vicinity"),
#                 "rating": place.get("rating"),
#                 "user_ratings_total": place.get("user_ratings_total"),
#                 "location": place.get("geometry", {}).get("location", {})
#             })

#         return results


# Tools/NearbyFacilitiesTool.py

import os
import googlemaps
from dotenv import load_dotenv

load_dotenv()

class NearbyFacilitiesTool:
    def __init__(self, api_key=None):
        # Load from .env if not provided
        self.api_key = api_key or os.getenv("GOOGLE_MAPS_API_KEY")
        self.gmaps = None
        if self.api_key:
            self.gmaps = googlemaps.Client(key=self.api_key)
        else:
            import logging
            logging.warning("Google Maps API key not set. NearbyFacilitiesTool will not function until configured.")

    def process(self, location, facility_type, radius=2000):
        """
        Find nearby facilities (schools, hospitals, etc.).
        
        Args:
            location (str): Address or place name (will be geocoded).
            facility_type (str): e.g. 'hospital', 'school', 'restaurant'
            radius (int): Search radius in meters (default: 2000m)

        Returns:
            list of dicts: Nearby facility info
        """
        if not self.gmaps:
            return {"error": "Google Maps API key not configured. Please set GOOGLE_MAPS_API_KEY."}
        
        # Convert location into lat/lng
        geocode_result = self.gmaps.geocode(location)
        if not geocode_result:
            return {"error": f"Could not geocode location: {location}"}
        
        latlng = geocode_result[0]["geometry"]["location"]

        # Normalize user-friendly/plural facility types to Google Places supported types.
        raw_type = str(facility_type or "").strip().lower()
        type_aliases = {
            "schools": "school",
            "school": "school",
            "colleges": "university",
            "college": "university",
            "hospitals": "hospital",
            "hospital": "hospital",
            "restaurants": "restaurant",
            "restaurant": "restaurant",
            "malls": "shopping_mall",
            "mall": "shopping_mall",
        }
        mapped_type = type_aliases.get(raw_type, raw_type or "school")

        # Search nearby places by type first.
        places = self.gmaps.places_nearby(
            location=(latlng["lat"], latlng["lng"]),
            radius=radius,
            type=mapped_type
        )

        # Fallback: text search for broader matching if typed nearby returns nothing.
        if not places.get("results"):
            query = f"{raw_type or mapped_type} near {location}"
            places = self.gmaps.places(query=query)

        results = []
        for place in places.get("results", []):
            results.append({
                "name": place.get("name"),
                "address": place.get("vicinity"),
                "rating": place.get("rating"),
                "user_ratings_total": place.get("user_ratings_total"),
                "location": place.get("geometry", {}).get("location", {})
            })

        return results
