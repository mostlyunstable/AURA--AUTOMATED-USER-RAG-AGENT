import os


def resolve_within_directory(base_dir: str, requested_path: str) -> str | None:
    """Resolve requested_path against base_dir and ensure containment.

    Returns the canonical (symlink-resolved) absolute path when the target
    is inside base_dir, otherwise None.

    Uses os.path.commonpath instead of str.startswith so that sibling
    directories sharing a string prefix (e.g. /worktree vs /worktree-other)
    are correctly rejected. Both sides are symlink-resolved so a symlink
    inside the directory pointing outside is also rejected.
    """
    if not base_dir or not requested_path:
        return None

    base_abs = os.path.abspath(base_dir)
    if os.path.isabs(requested_path):
        target_abs = os.path.abspath(requested_path)
    else:
        target_abs = os.path.abspath(os.path.join(base_abs, requested_path))

    # Fast lexical check first (also rejects ".." escapes).
    try:
        if os.path.commonpath([base_abs, target_abs]) != base_abs:
            return None
    except ValueError:
        return None

    # Resolve symlinks on both sides and re-check.
    try:
        base_real = os.path.realpath(base_abs)
        target_real = os.path.realpath(target_abs)
    except Exception:
        return None

    try:
        if os.path.commonpath([base_real, target_real]) != base_real:
            return None
    except ValueError:
        return None

    return target_real
