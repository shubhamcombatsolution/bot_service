
import os
import googlemaps
from datetime import datetime, timedelta
from .BaseTool import BaseTool

class CommuteTimeTool(BaseTool):
    """
    Tool to calculate commute time between two locations based on different time slots during the day.
    """

    def __init__(self, api_key=None):
        super().__init__(
            name="Commute Time Tool",
            description="Calculate commute time between the user's location and the property site based on different time slots."
        )
        # Fetch API key from environment variable if not provided
        self.api_key = api_key or os.getenv("GOOGLE_MAPS_API_KEY")
        if not self.api_key:
            raise ValueError("Google Maps API key is required. Set it via parameter or environment variable 'GOOGLE_MAPS_API_KEY'.")

        self.gmaps = googlemaps.Client(key=self.api_key)

    def get_commute_time_for_slot(self, start_hour, end_hour):
        """
        Returns the time slot as a string based on start and end hours.
        """
        return f"{start_hour} am - {end_hour} am" if end_hour < 12 else f"{start_hour} pm - {end_hour} pm"

    def _format_duration(self, minutes: float) -> str:
        """
        Formats duration into hours/days instead of raw minutes.
        """
        total_minutes = int(round(minutes))
        if total_minutes < 60:
            return "under 1 hour"
        total_hours = total_minutes / 60.0
        if total_hours < 24:
            return f"{total_hours:.1f} hours"
        total_days = total_hours / 24.0
        return f"{total_days:.1f} days ({total_hours:.1f} hours)"

    def process(self, origin, destination, future_date_str):
        """
        Calculate the commute time for multiple time slots during the day based on the user's future date.
        """
        try:
            future_date = datetime.strptime(future_date_str, '%Y-%m-%d')
            time_slots = [(7, 9), (9, 11), (11, 13), (13, 15), (15, 17), (17, 19)]
            results = []

            best_distance_text = None
            best_distance_km = None
            best_duration_mins = None

            for start_hour, end_hour in time_slots:
                departure_time = datetime.combine(future_date, datetime.min.time()) + timedelta(hours=start_hour)
                if departure_time < datetime.now():
                    departure_time = datetime.now() + timedelta(minutes=1)

                time_slot = self.get_commute_time_for_slot(start_hour, end_hour)
                distance_matrix = self.gmaps.distance_matrix(
                    origin, destination, mode="driving",
                    departure_time=departure_time, traffic_model="best_guess"
                )

                if 'rows' not in distance_matrix or not distance_matrix['rows']:
                    results.append(f"Error: Unable to calculate distance matrix for {time_slot}.")
                    continue

                element = distance_matrix['rows'][0]['elements'][0]
                if 'duration_in_traffic' not in element or 'distance' not in element:
                    results.append(f"Error: Unable to retrieve commute time or distance for {time_slot}.")
                    continue

                commute_time_minutes = element['duration_in_traffic']['value'] / 60
                distance_text = element.get('distance', {}).get('text')
                distance_meters = element.get('distance', {}).get('value')
                if distance_text and best_distance_text is None:
                    best_distance_text = distance_text
                if isinstance(distance_meters, (int, float)):
                    km = round(float(distance_meters) / 1000.0, 1)
                    if best_distance_km is None:
                        best_distance_km = km
                if best_duration_mins is None or commute_time_minutes < best_duration_mins:
                    best_duration_mins = commute_time_minutes

                return_note = " (Return)" if start_hour >= 15 else ""
                results.append(f"{time_slot}: {self._format_duration(commute_time_minutes)}{return_note}")

            header_parts = []
            if best_distance_km is not None:
                header_parts.append(f"Approx distance: {best_distance_km:.1f} km")
            elif best_distance_text:
                header_parts.append(f"Approx distance: {best_distance_text}")
            if best_duration_mins is not None:
                header_parts.append(f"Fastest commute window: ~{best_duration_mins:.0f} mins")

            if header_parts:
                if best_duration_mins is not None:
                    # Replace minute text with formatted hours/days.
                    header_parts = [
                        part for part in header_parts
                        if not part.startswith("Fastest commute window:")
                    ]
                    header_parts.append(
                        f"Fastest commute window: ~{self._format_duration(best_duration_mins)}"
                    )
                return {"message": f"{' | '.join(header_parts)}\n" + "\n".join(results)}
            return {"message": "\n".join(results)}

        except Exception as e:
            return {"message": f"Error calculating commute times: {e}"}
