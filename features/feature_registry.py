from __future__ import annotations

from typing import Iterable


class FeatureRegistry:
    """Central registry for feature lifecycle events."""

    def __init__(self) -> None:
        self._features = []

    @property
    def features(self) -> list:
        return self._features

    def register(self, feature, app, parent) -> None:
        # Features should not build persistent UI; tabs/modules handle UI.
        self._features.append(feature)

    def register_many(self, features: Iterable, app, parent) -> None:
        for feature in features:
            self.register(feature, app, parent)

    def unregister(self, feature) -> None:
        try:
            self._features.remove(feature)
        except ValueError:
            pass

    def list(self) -> list:
        return list(self._features)

    def notify_file_opened(self, app, root_file) -> None:
        for feature in self._features:
            feature.on_file_opened(app, root_file)

    def notify_selection(self, app, obj, path: str) -> None:
        for feature in self._features:
            feature.on_selection(app, obj, path)

    def notify_directory_opened(self, app, directory, path: str) -> None:
        for feature in self._features:
            feature.on_directory_opened(app, directory, path)
