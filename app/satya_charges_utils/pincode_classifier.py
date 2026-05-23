# satya_charges_utils/pincode_classifier.py

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from rapidfuzz import fuzz, process
from logging_config import setup_logging

logger = setup_logging(
    name="pincode-classifier",
    level="DEBUG",
    group="charges"
)



# -------------------------------------------------------------------
# HTTP session with retries
# -------------------------------------------------------------------
def _get_http_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
    )
    session.mount("http://", HTTPAdapter(max_retries=retry))
    return session


# -------------------------------------------------------------------
# Fetch pincode details
# -------------------------------------------------------------------
def get_pincode_details(pincode: str) -> dict | None:
    url = f"http://api.postalpincode.in/pincode/{pincode}"
    session = _get_http_session()

    try:
        logger.debug(f"Fetching pincode details for pincode={pincode}")

        response = session.get(
            url,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()

        data = response.json()
        post_offices = data[0].get("PostOffice", [])

        if not post_offices:
            logger.warning(f"No PostOffice data for pincode={pincode}")
            return None

        details = {
            "blocks": list(
                {po.get("Block") for po in post_offices if po.get("Block")}
            ),
            "district": post_offices[0].get("District"),
            "state": post_offices[0].get("State"),
        }

        logger.debug(f"Pincode details resolved: {details}")
        return details

    except Exception as exc:
        logger.exception(f"Failed to fetch pincode details: {exc}")
        return None


# -------------------------------------------------------------------
# Fuzzy matching helper
# -------------------------------------------------------------------
def _fuzzy_in(item: str, choices: list[str], threshold: int = 80) -> bool:
    if not item:
        return False

    result = process.extractOne(
        item.lower(),
        [c.lower() for c in choices],
        scorer=fuzz.token_sort_ratio,
    )

    return bool(result and result[1] >= threshold)


# -------------------------------------------------------------------
# Main classification function
# -------------------------------------------------------------------
def classify_pincode_location(
    pincode: str,
    current_city: str,
    current_state: str,
) -> str:
    """
    Returns one of:
    - within_city
    - within_metro
    - within_state
    - within_zone
    - special_destination
    - rest_of_india
    """

    logger.info(f"Classifying pincode={pincode}")

    details = get_pincode_details(pincode)
    if not details:
        return "unknown"

    blocks = [b.lower() for b in details["blocks"]]
    district = (details["district"] or "").lower()
    state = (details["state"] or "").lower()

    metro_cities = [
        "delhi", "mumbai", "kolkata", "chennai",
        "bangalore", "hyderabad", "ahmedabad",
        "pune", "navi mumbai",
    ]

    southern_zone_states = [
        "karnataka", "kerala", "tamil nadu",
        "telangana", "andhra pradesh",
    ]

    southern_zone_ut = ["puducherry", "lakshadweep"]

    special_destinations = [
        "jammu and kashmir", "j&k",
        "arunachal pradesh", "assam", "nagaland",
        "meghalaya", "manipur", "tripura",
        "andaman and nicobar",
    ]

    # ------------------ Decision Tree ------------------

    if _fuzzy_in(district, [current_city]) or any(
        _fuzzy_in(block, [current_city]) for block in blocks
    ):
        logger.debug("Matched: within_city")
        return "within_city"

    if _fuzzy_in(district, metro_cities) or any(
        _fuzzy_in(block, metro_cities) for block in blocks
    ):
        logger.debug("Matched: within_metro")
        return "within_metro"

    if _fuzzy_in(state, special_destinations):
        logger.debug("Matched: special_destination")
        return "special_destination"

    if _fuzzy_in(state, [current_state]):
        logger.debug("Matched: within_state")
        return "within_state"

    if _fuzzy_in(state, southern_zone_states + southern_zone_ut):
        logger.debug("Matched: within_zone")
        return "within_zone"

    logger.debug("Matched: rest_of_india")
    return "rest_of_india"
