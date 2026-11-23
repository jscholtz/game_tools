"""Read-only access to the Streamlit application's bestiary collections."""

import os
import threading

from pymongo import MongoClient

from tab_views.data_models import BestiaryEntry, CustomCreature, StandardCreature
from tab_views.statblock_renderer.standard import adapt_standard_creature

INDEX_FIELDS = {
    "_id": 0, "slug": 1, "name": 1, "type": 1, "size": 1,
    "challenge_rating": 1, "cr": 1, "document__title": 1, "hit_points": 1,
}
MAX_ENTRIES = 10000
_client = None
_client_lock = threading.Lock()


class BestiaryConfigurationError(Exception):
    pass


class BestiaryLimitError(Exception):
    pass


def get_client():
    global _client
    with _client_lock:
        if _client is None:
            uri = os.environ.get("MONGODB_URI", "").strip()
            if not uri:
                raise BestiaryConfigurationError("MONGODB_URI is not configured.")
            _client = MongoClient(uri, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000)
        return _client


def load_index():
    client = get_client()
    standard = [
        BestiaryEntry.model_validate(document)
        for document in client["creatures"]["basic_list"].find({}, INDEX_FIELDS).limit(MAX_ENTRIES + 1)
    ]
    if len(standard) > MAX_ENTRIES:
        raise BestiaryLimitError
    if any(
        not entry.slug or len(entry.slug) > 512 or "\x00" in entry.slug or entry.slug.startswith("custom:")
        for entry in standard
    ):
        raise ValueError("Invalid standard creature identifier.")
    custom = []
    for document in client["game_helper"]["custom_bestiary"].find().limit(MAX_ENTRIES + 1):
        identifier = document.pop("_id")
        creature = CustomCreature.model_validate(document)
        if (identifier != creature.slug or not creature.slug.startswith("custom:")
                or len(creature.slug) > 512 or "\x00" in creature.slug):
            raise ValueError("Invalid custom creature identifier.")
        custom.append(creature.as_bestiary_entry())
        if len(standard) + len(custom) > MAX_ENTRIES:
            raise BestiaryLimitError
    entries = standard + custom
    slugs = [entry.slug for entry in entries]
    if len(set(slugs)) != len(slugs):
        raise ValueError("Bestiary contains duplicate creature identifiers.")
    return sorted(entries, key=lambda entry: (entry.name.casefold(), entry.document__title, entry.slug))


def load_creature(slug):
    client = get_client()
    if slug.startswith("custom:"):
        document = client["game_helper"]["custom_bestiary"].find_one({"_id": slug}, {"_id": 0})
        if document is None:
            return None
        creature = CustomCreature.model_validate(document)
        return creature, creature.initiative_bonus
    document = client["creatures"]["basic_list"].find_one({"slug": slug}, {"_id": 0})
    if document is None:
        return None
    creature = StandardCreature.model_validate(document)
    return adapt_standard_creature(creature), creature.initiative_bonus
