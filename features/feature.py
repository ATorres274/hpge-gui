class Feature:
    """Base feature: provides action handlers only.

    Features must not build or own persistent UI. Tabs/modules are
    responsible for creating UI and delegating actions to features.
    """
    name = "Feature"

    def on_file_opened(self, app, root_file) -> None:
        """Called when a ROOT file is opened."""
        return None

    def on_selection(self, app, obj, path: str) -> None:
        """Called when the user selects an object in the browser."""
        return None

    def on_directory_opened(self, app, directory, path: str) -> None:
        """Called when a directory node is opened in the browser."""
        return None
