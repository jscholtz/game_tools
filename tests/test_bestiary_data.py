import unittest

from pymongo import MongoClient

from tab_views.config import get_required_env
from tab_views.data_models import BestiaryDisplay, BestiaryEntry
from tab_views.database import BESTIARY_DISPLAY_FIELDS, BESTIARY_INDEX_FIELDS


class BestiaryDataTest(unittest.TestCase):
    def test_all_entries_and_displays_match_models(self) -> None:
        with MongoClient(get_required_env("MONGODB_URI"), serverSelectionTimeoutMS=10_000) as client:
            database = client["creatures"]
            entries = list(database["basic_list"].find({}, BESTIARY_INDEX_FIELDS))
            displays = list(database["display"].find(
                {}, {**BESTIARY_DISPLAY_FIELDS, "slug": 1}
            ))
            self.assertTrue(entries, "Bestiary index is empty.")
            self.assertTrue(displays, "Bestiary display collection is empty.")

            entry_slugs = set()
            display_slugs = set()
            for entry in entries:
                with self.subTest(collection="basic_list", slug=entry.get("slug")):
                    entry_slugs.add(BestiaryEntry.model_validate(entry).slug)
            for display in displays:
                with self.subTest(collection="display", slug=display.get("slug")):
                    BestiaryDisplay.model_validate(display)
                    self.assertIsInstance(display.get("slug"), str)
                    display_slugs.add(display["slug"])
            self.assertFalse(
                entry_slugs - display_slugs,
                f"Bestiary entries missing displays: {sorted(entry_slugs - display_slugs)}",
            )


if __name__ == "__main__":
    unittest.main()
