"""Matcher plugin registry for the localization playground."""

from .akaze import AKAZEMatcher

MATCHERS = {
    AKAZEMatcher.name: AKAZEMatcher,
}


def available_matchers() -> dict[str, type]:
    return {
        name: cls
        for name, cls in MATCHERS.items()
        if cls.is_available()
    }
