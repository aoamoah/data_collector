from pathlib import Path, PureWindowsPath

PROJECT_ROOT = Path(__file__).parent.parent.parent


def resolve_data_path(stored: str | None) -> str | None:
    """Resolve a stored file path against the current project location.

    Paths are stored absolute, so a database moved from another machine or
    OS points at locations that no longer exist. If the stored path is
    missing, everything after the top-level data folder is re-rooted onto
    this project directory. Returns None when the file cannot be found.
    """
    if not stored:
        return None
    if Path(stored).exists():
        return stored

    # PureWindowsPath splits on both / and \ separators
    parts = PureWindowsPath(stored).parts
    for anchor in ("data", "dataset"):
        if anchor in parts:
            idx = len(parts) - 1 - parts[::-1].index(anchor)
            candidate = PROJECT_ROOT.joinpath(*parts[idx:])
            if candidate.exists():
                return str(candidate)
    return None
