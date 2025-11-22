#!/usr/bin/env python3
"""
City Name Resolver - Convert Hebrew/English city names to internal file names.

This module provides bidirectional mapping between:
- Hebrew city names (e.g., "תל אביב")
- English variations (e.g., "Tel Aviv", "Tel Aviv-Yafo")
- Internal file names (e.g., "tel_aviv")
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)


class CityNameResolver:
    """Resolve city names from Hebrew/English to internal file names."""

    def __init__(self, mapping_file: Optional[str] = None):
        """
        Initialize resolver with city names mapping.

        Args:
            mapping_file: Path to JSON mapping file. If None, uses default location.
        """
        if mapping_file is None:
            # Default location
            mapping_file = Path(__file__).parent.parent / "data" / "processed" / "israel" / "city_names_mapping.json"

        self.mapping_file = Path(mapping_file)
        self.city_mapping: Dict = {}
        self.hebrew_to_file: Dict[str, str] = {}
        self.english_to_file: Dict[str, str] = {}

        self._load_mapping()

    def _load_mapping(self):
        """Load city names mapping from JSON file."""
        try:
            if not self.mapping_file.exists():
                logger.warning(f"City mapping file not found: {self.mapping_file}")
                return

            with open(self.mapping_file, "r", encoding="utf-8") as f:
                self.city_mapping = json.load(f)

            # Build reverse lookup dictionaries
            for file_name, data in self.city_mapping.items():
                # Hebrew to file name
                hebrew = data.get("hebrew", "")
                if hebrew and not hebrew.startswith("[TO_FILL"):
                    self.hebrew_to_file[hebrew] = file_name
                    self.hebrew_to_file[hebrew.lower()] = file_name

                # English variations to file name
                english_names = data.get("english", [])
                for eng_name in english_names:
                    self.english_to_file[eng_name.lower()] = file_name

            logger.info(f"Loaded {len(self.city_mapping)} city mappings")
            logger.info(f"  Hebrew lookups: {len(self.hebrew_to_file)}")
            logger.info(f"  English lookups: {len(self.english_to_file)}")

        except Exception as e:
            logger.error(f"Failed to load city mapping: {e}")

    def resolve(self, city_name: str) -> Optional[str]:
        """
        Resolve city name to internal file name.

        Args:
            city_name: City name in Hebrew, English, or any variation

        Returns:
            Internal file name (e.g., "tel_aviv") or None if not found
        """
        if not city_name:
            return None

        # Try exact match (already normalized)
        if city_name in self.city_mapping:
            return city_name

        # Try Hebrew lookup
        if city_name in self.hebrew_to_file:
            return self.hebrew_to_file[city_name]

        # Try English lookup (case-insensitive)
        lower_name = city_name.lower()
        if lower_name in self.english_to_file:
            return self.english_to_file[lower_name]

        # Try fuzzy matching (remove common variations)
        normalized = self._normalize_name(city_name)
        if normalized in self.english_to_file:
            return self.english_to_file[normalized]

        logger.debug(f"Could not resolve city name: {city_name}")
        return None

    def _normalize_name(self, name: str) -> str:
        """
        Normalize city name for fuzzy matching.

        Handles common variations like:
        - "Tel Aviv-Yafo" → "tel aviv"
        - "Be'er Sheva" → "beer sheva"
        """
        # Convert to lowercase
        normalized = name.lower()

        # Remove punctuation
        normalized = normalized.replace("-", " ").replace("'", "")

        # Remove extra spaces
        normalized = " ".join(normalized.split())

        return normalized

    def get_hebrew_name(self, file_name: str) -> Optional[str]:
        """
        Get Hebrew name for a city file name.

        Args:
            file_name: Internal file name (e.g., "tel_aviv")

        Returns:
            Hebrew name or None if not found
        """
        if file_name not in self.city_mapping:
            return None

        hebrew = self.city_mapping[file_name].get("hebrew", "")
        if hebrew and not hebrew.startswith("[TO_FILL"):
            return hebrew

        return None

    def get_english_names(self, file_name: str) -> List[str]:
        """
        Get all English name variations for a city.

        Args:
            file_name: Internal file name (e.g., "tel_aviv")

        Returns:
            List of English names
        """
        if file_name not in self.city_mapping:
            return []

        return self.city_mapping[file_name].get("english", [])

    def get_all_cities(self) -> List[str]:
        """Get list of all known city file names."""
        return list(self.city_mapping.keys())


# Global resolver instance
_resolver: Optional[CityNameResolver] = None


def get_resolver() -> CityNameResolver:
    """Get or create global city name resolver instance."""
    global _resolver
    if _resolver is None:
        _resolver = CityNameResolver()
    return _resolver


def resolve_city_name(city_name: str) -> Optional[str]:
    """
    Convenience function to resolve city name.

    Args:
        city_name: City name in Hebrew or English

    Returns:
        Internal file name or None
    """
    resolver = get_resolver()
    return resolver.resolve(city_name)


# Example usage
if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)

    resolver = CityNameResolver()

    # Test cases
    test_names = [
        "תל אביב",
        "Tel Aviv",
        "Tel Aviv-Yafo",
        "חיפה",
        "Haifa",
        "ירושלים",
        "Jerusalem",
        "באר שבע",
        "Beer Sheva",
        "Beersheba",
    ]

    print("\nCity Name Resolution Tests:")
    print("=" * 60)
    for name in test_names:
        resolved = resolver.resolve(name)
        if resolved:
            hebrew = resolver.get_hebrew_name(resolved)
            english = resolver.get_english_names(resolved)
            print(f"\nInput: {name}")
            print(f"  File: {resolved}")
            print(f"  Hebrew: {hebrew}")
            print(f"  English: {', '.join(english)}")
        else:
            print(f"\nCould not resolve: {name}")
