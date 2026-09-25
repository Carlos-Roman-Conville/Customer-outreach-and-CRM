"""
Overture taxonomy → revenue tier classification.

Resolve most-specific-first: leaf override → L2 rule → L1 root rule → category fallback → U.
"""
from __future__ import annotations

from typing import Literal

from config import KNOWN_BOOKING_VENDORS

RevenueTier = Literal["A", "B", "C", "U", "X"]
ClassificationSource = Literal["leaf", "l2", "l1", "fallback"]

REVENUE_TIER_TO_SEGMENT: dict[str, str] = {
    "A": "tier1_high_value",
    "B": "tier2_mid_value",
    "C": "tier3_low_value",
    "U": "unclassified",
    "X": "excluded",
}

REVENUE_TIER_BASE_SCORE: dict[str, float] = {
    "A": 30.0,
    "B": 10.0,
    "C": 0.0,
    "U": 0.0,
    "X": -100.0,
}

# L1 roots that are never buyers
L1_EXCLUDE: frozenset[str] = frozenset({
    "education",
    "community_and_government",
    "cultural_and_historic",
    "geographic_entities",
})

# (l1, l2) → tier for all observed level-2 nodes
L2_TIERS: dict[tuple[str, str], RevenueTier] = {
    # arts_and_entertainment
    ("arts_and_entertainment", "performing_arts_venue"): "B",
    ("arts_and_entertainment", "arts_and_crafts_space"): "B",
    ("arts_and_entertainment", "museum"): "X",
    ("arts_and_entertainment", "event_venue"): "A",
    ("arts_and_entertainment", "stadium_arena"): "X",
    ("arts_and_entertainment", "social_club"): "B",
    ("arts_and_entertainment", "gaming_venue"): "C",
    ("arts_and_entertainment", "nightlife_venue"): "C",
    ("arts_and_entertainment", "amusement_attraction"): "X",
    ("arts_and_entertainment", "movie_theater"): "X",
    ("arts_and_entertainment", "festival_venue"): "B",
    ("arts_and_entertainment", "spiritual_advising"): "B",
    ("arts_and_entertainment", "animal_attraction"): "X",
    ("arts_and_entertainment", "science_attraction"): "X",
    ("arts_and_entertainment", "ticket_office_or_booth"): "X",
    ("arts_and_entertainment", "rural_attraction"): "X",
    # food_and_drink
    ("food_and_drink", "restaurant"): "C",
    ("food_and_drink", "casual_eatery"): "C",
    ("food_and_drink", "alcoholic_beverage_venue"): "C",
    ("food_and_drink", "non_alcoholic_beverage_venue"): "C",
    # health_care
    ("health_care", "outpatient_care_facility"): "A",
    ("health_care", "medical_service"): "A",
    ("health_care", "specialized_medical_facility"): "A",
    ("health_care", "hospital"): "X",
    ("health_care", "emergency_or_urgent_care_facility"): "A",
    # lifestyle_services
    ("lifestyle_services", "personal_or_beauty_service"): "B",
    ("lifestyle_services", "wellness_service"): "B",
    ("lifestyle_services", "animal_or_pet_service"): "B",
    ("lifestyle_services", "beauty_service"): "B",
    ("lifestyle_services", "food_service"): "C",
    # lodging
    ("lodging", "hotel"): "B",
    ("lodging", "campground"): "X",
    ("lodging", "bed_and_breakfast"): "B",
    ("lodging", "resort"): "B",
    ("lodging", "lodge"): "B",
    ("lodging", "inn"): "B",
    ("lodging", "private_lodging"): "U",
    ("lodging", "rv_park"): "X",
    ("lodging", "service_apartment"): "B",
    ("lodging", "cabin"): "B",
    ("lodging", "hostel"): "B",
    ("lodging", "cottage"): "B",
    ("lodging", "retreat"): "B",
    # services_and_business
    ("services_and_business", "home_service"): "A",
    ("services_and_business", "financial_service"): "A",
    ("services_and_business", "real_estate_service"): "A",
    ("services_and_business", "b2b_service"): "B",
    ("services_and_business", "professional_service"): "A",
    ("services_and_business", "legal_service"): "A",
    ("services_and_business", "event_or_party_service"): "A",
    ("services_and_business", "real_estate"): "A",
    ("services_and_business", "media_service"): "B",
    ("services_and_business", "technical_service"): "B",
    ("services_and_business", "family_service"): "B",
    ("services_and_business", "housing_or_property_service"): "X",
    ("services_and_business", "shipping_or_delivery_service"): "B",
    ("services_and_business", "building_or_construction_service"): "A",
    ("services_and_business", "storage_facility"): "X",
    ("services_and_business", "corporate_or_business_office"): "U",
    ("services_and_business", "design_service"): "B",
    ("services_and_business", "laundry_service"): "B",
    ("services_and_business", "business"): "U",
    ("services_and_business", "printing_service"): "B",
    ("services_and_business", "agricultural_service"): "B",
    ("services_and_business", "environmental_or_ecological_service"): "B",
    ("services_and_business", "telecommunications_service"): "B",
    ("services_and_business", "rental_service"): "B",
    ("services_and_business", "security_service"): "A",
    ("services_and_business", "industrial_facility_or_service"): "B",
    # shopping
    ("shopping", "specialty_store"): "C",
    ("shopping", "fashion_and_apparel_store"): "C",
    ("shopping", "food_and_beverage_store"): "X",
    ("shopping", "vehicle_dealer"): "A",
    ("shopping", "convenience_store"): "X",
    ("shopping", "second_hand_store"): "C",
    ("shopping", "discount_store"): "X",
    ("shopping", "market"): "C",
    ("shopping", "shopping_mall"): "X",
    ("shopping", "department_store"): "X",
    ("shopping", "warehouse_club_store"): "X",
    ("shopping", "superstore"): "X",
    ("shopping", "kiosk"): "X",
    ("shopping", "shopping_service"): "C",
    # sports_and_recreation
    ("sports_and_recreation", "sport_or_fitness_facility"): "B",
    ("sports_and_recreation", "park"): "X",
    ("sports_and_recreation", "sport_or_recreation_club"): "B",
    ("sports_and_recreation", "recreational_trail_or_path"): "X",
    ("sports_and_recreation", "sport_league"): "X",
    ("sports_and_recreation", "sport_team"): "X",
    ("sports_and_recreation", "recreational_equipment_rental"): "B",
    # travel_and_transportation
    ("travel_and_transportation", "vehicle_service"): "A",
    ("travel_and_transportation", "fueling_station"): "X",
    ("travel_and_transportation", "travel_service"): "B",
    ("travel_and_transportation", "ground_transport_facility_or_service"): "B",
    ("travel_and_transportation", "parking"): "X",
    ("travel_and_transportation", "air_transport_facility_or_service"): "X",
    ("travel_and_transportation", "water_transport_facility_or_service"): "X",
}

# L1 defaults for root-only rows (single-node hierarchy)
L1_TIERS: dict[str, RevenueTier] = {
    "arts_and_entertainment": "B",
    "food_and_drink": "C",
    "health_care": "A",
    "lifestyle_services": "B",
    "lodging": "B",
    "services_and_business": "A",
    "shopping": "C",
    "sports_and_recreation": "B",
    "travel_and_transportation": "A",
}

# Full path overrides (l1/l2/leaf or l1/l2/l3/...) — only where leaf differs from L2 default
LEAF_TIERS: dict[str, RevenueTier] = {
    # home_service branch
    "services_and_business/home_service/home_cleaning": "B",
    "services_and_business/home_service/interior_design": "B",
    "services_and_business/home_service/window_washing": "B",
    "services_and_business/home_service/carpet_cleaning": "B",
    "services_and_business/home_service/organization_service": "B",
    # financial_service — exclude banks / transfers
    "services_and_business/financial_service/bank_or_credit_union": "X",
    "services_and_business/financial_service/bank": "X",
    "services_and_business/financial_service/credit_union": "X",
    "services_and_business/financial_service/money_transfer_service": "X",
    "services_and_business/financial_service/trusts": "X",
    # housing — all residential
    "services_and_business/housing_or_property_service/retirement_home": "X",
    "services_and_business/housing_or_property_service/apartment": "X",
    "services_and_business/housing_or_property_service/assisted_living_facility": "X",
    "services_and_business/housing_or_property_service/condominium": "X",
    "services_and_business/housing_or_property_service/mobile_home_park": "X",
    "services_and_business/housing_or_property_service/halfway_house": "X",
    "services_and_business/housing_or_property_service/university_housing": "X",
    # family_service
    "services_and_business/family_service/day_care_preschool": "X",
    "services_and_business/family_service/child_care_and_day_care": "X",
    "services_and_business/family_service/funeral_service": "A",
    # technical_service
    "services_and_business/technical_service/software_development": "X",
    "services_and_business/technical_service/internet_service_provider": "X",
    # specialty_store
    "shopping/specialty_store/pharmacy": "X",
    "shopping/specialty_store/grocery_store": "X",
    "shopping/specialty_store/building_supply_store": "B",
    "shopping/specialty_store/auto_parts_store": "B",
    "shopping/specialty_store/nursery_and_gardening_store": "B",
    "shopping/specialty_store/hardware_store": "B",
    "shopping/specialty_store/mobile_phone_store": "C",
    "shopping/specialty_store/discount_store": "X",
    # sport_or_fitness_facility — municipal / facilities
    "sports_and_recreation/sport_or_fitness_facility/baseball_field": "X",
    "sports_and_recreation/sport_or_fitness_facility/skate_park": "X",
    "sports_and_recreation/sport_or_fitness_facility/swimming_pool": "X",
    "sports_and_recreation/sport_or_fitness_facility/golf_course": "X",
    "sports_and_recreation/sport_or_fitness_facility/equestrian_facility": "X",
    "sports_and_recreation/sport_or_fitness_facility/sport_or_fitness_facility": "B",
    # outpatient — downgrade naturopathic
    "health_care/outpatient_care_facility/naturopathic_medicine": "B",
    "health_care/outpatient_care_facility/homeopathy": "B",
    # wellness — medical spa is higher value
    "lifestyle_services/wellness_service/medical_spa": "A",
    # b2b — manufacturers less ideal
    "services_and_business/b2b_service/industrial_equipment_manufacturer": "C",
    "services_and_business/b2b_service/manufacturer": "C",
    "services_and_business/b2b_service/chemical_plant": "X",
}

# Fallback when taxonomy is missing — exact match on businesses.category
CATEGORY_FALLBACK: dict[str, RevenueTier] = {
    "plumbing": "A",
    "electrician": "A",
    "hvac_services": "A",
    "hvac_service": "A",
    "contractor": "A",
    "roofing": "A",
    "landscaping": "A",
    "automotive_repair": "A",
    "auto_body_shop": "A",
    "dentist": "A",
    "general_dentistry": "A",
    "chiropractor": "A",
    "lawyer": "A",
    "real_estate_agent": "A",
    "insurance_agency": "A",
    "physical_therapy": "A",
    "home_health_care": "A",
    "car_dealer": "A",
    "hair_salon": "B",
    "nail_salon": "B",
    "barber": "B",
    "beauty_salon": "B",
    "gym": "B",
    "pizza_restaurant": "C",
    "restaurant": "C",
    "coffee_shop": "C",
    "bakery": "C",
    "park": "X",
    "landmark_and_historical_building": "X",
    "convenience_store": "X",
    "gas_station": "X",
    "grocery_store": "X",
    "pharmacy": "X",
    "elementary_school": "X",
    "high_school": "X",
    "middle_school": "X",
    "baptist_church": "X",
    "professional_services": "A",
    "home_service": "A",
    "construction_services": "A",
    "event_planning": "A",
    "financial_service": "A",
    "medical_center": "A",
    "counseling_and_mental_health": "A",
}


def parse_taxonomy(taxonomy: str | None) -> list[str]:
    """Extract hierarchy list from Overture taxonomy blob."""
    if not taxonomy:
        return []
    idx = taxonomy.find("hierarchy")
    if idx < 0:
        return []
    start = taxonomy.find("[", idx)
    end = taxonomy.find("]", start)
    if start < 0 or end < 0:
        return []
    return [part.strip() for part in taxonomy[start + 1 : end].split(",") if part.strip()]


def _path_string(hierarchy: list[str]) -> str:
    return "/".join(hierarchy)


def classify_business(
    taxonomy: str | None,
    category: str | None,
) -> tuple[RevenueTier, str, str, ClassificationSource]:
    """
    Return (revenue_tier, segment, category_path, classification_source).
    """
    hierarchy = parse_taxonomy(taxonomy)

    if hierarchy:
        path = _path_string(hierarchy)
        l1 = hierarchy[0]

        if l1 in L1_EXCLUDE:
            return "X", REVENUE_TIER_TO_SEGMENT["X"], path, "l1"

        # Leaf path overrides (try longest prefixes first)
        for depth in range(len(hierarchy), 1, -1):
            prefix = _path_string(hierarchy[:depth])
            if prefix in LEAF_TIERS:
                tier = LEAF_TIERS[prefix]
                return tier, REVENUE_TIER_TO_SEGMENT[tier], path, "leaf"

        if len(hierarchy) >= 2:
            l2_key = (l1, hierarchy[1])
            if l2_key in L2_TIERS:
                tier = L2_TIERS[l2_key]
                return tier, REVENUE_TIER_TO_SEGMENT[tier], path, "l2"

        if l1 in L1_TIERS:
            tier = L1_TIERS[l1]
            return tier, REVENUE_TIER_TO_SEGMENT[tier], path, "l1"

        return "U", REVENUE_TIER_TO_SEGMENT["U"], path, "l1"

    # No taxonomy — category fallback
    cat = (category or "").strip()
    if cat and cat in CATEGORY_FALLBACK:
        tier = CATEGORY_FALLBACK[cat]
        return tier, REVENUE_TIER_TO_SEGMENT[tier], cat, "fallback"

    if cat:
        return "U", REVENUE_TIER_TO_SEGMENT["U"], cat, "fallback"

    return "U", REVENUE_TIER_TO_SEGMENT["U"], "", "fallback"


# SQL fragments for call queue ordering (revenue tier primary, fit score secondary)
QUEUE_ELIGIBLE_WHERE = "t.revenue_tier IN ('A', 'B', 'C', 'U')"

QUEUE_TIER_ORDER = """
CASE t.revenue_tier
    WHEN 'A' THEN 0
    WHEN 'B' THEN 1
    WHEN 'C' THEN 2
    ELSE 3
END
"""

_VENDORS = ", ".join(f"'{v}'" for v in sorted(KNOWN_BOOKING_VENDORS))
QUEUE_ORDER_BY = f"""
t.icp_score DESC,
b.review_count DESC NULLS LAST,
CASE WHEN b.booking_platform IN ({_VENDORS}) THEN 2
     WHEN b.booking_platform IS NOT NULL THEN 1
     ELSE 0 END DESC,
CASE WHEN b.business_creation_date > '1900-01-01'
     THEN b.business_creation_date END ASC NULLS LAST,
t.data_coverage DESC NULLS LAST,
substr(b.gers_id, -6) ASC
"""
