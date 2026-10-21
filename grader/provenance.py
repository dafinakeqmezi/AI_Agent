"""Bounded, read-only Git evidence for exact frozen file versions; no misconduct verdicts."""
import hashlib
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


LIMITATION = ("Commit timestamps are author-controlled and are not public availability dates. "
              "An earlier matching version does not prove authorship or copying direction. "
              "Shared templates, forks, collaboration and third-party sources require human review. "
              "Renamed files, edited matches, unavailable objects and bounded history may leave gaps.")


def date(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (ValueError, TypeError, AttributeError):
        return None


def observe(submission, path, digest, matcher=None):
    """Earliest recorded commit *containing this exact content*, not first path creation."""
    cache = submission.setdefault("_version_observations", {})
    key = (path, digest)
    if key in cache:
        return cache[key]
    result = {"status": "UNAVAILABLE", "commit": None, "author_date": None,
              "committer_date": None, "history_complete": False}
    cache[key] = result
    source = submission.get("source_path")
    if not source or Path(path).is_absolute() or ".." in PurePosixPath(path).parts or "\\" in path:
        return result
    repo = Path(source)
    if not (repo / ".git").exists():
        return result
    candidates = [c for c in submission.get("commits", []) if path in (c.get("paths") or [])]
    checked = 0
    observations = []
    deadline = submission.setdefault("_provenance_deadline", time.monotonic() + 5)
    for commit in candidates[:100]:
        if time.monotonic() >= deadline:
            break
        sha = commit.get("sha", "")
        if not re.fullmatch(r"[a-fA-F0-9]{40,64}", sha):
            continue
        try:
            # cat-file reads raw blobs: no checkout, filters, diff drivers or student code.
            args = ["git", "--no-replace-objects", "-C", str(repo), "cat-file"]
            spec = sha + ":" + path
            size = subprocess.run(args + ["-s", spec], capture_output=True, timeout=2)
            if size.returncode or int(size.stdout) > 256_000:
                continue
            blob = subprocess.run(args + ["blob", spec], capture_output=True, timeout=2)
            if blob.returncode:
                continue
            checked += 1
            if (matcher(blob.stdout) if matcher else hashlib.sha256(blob.stdout).hexdigest() == digest):
                observations.append(commit)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            continue
    result["history_complete"] = checked == len(candidates) and bool(candidates)
    dated = [c for c in observations if date(c.get("committer_date"))]
    if dated:
        first = min(dated, key=lambda c: date(c["committer_date"]))
        result.update(status="MATCH_OBSERVED", commit=first["sha"], author_date=first.get("author_date"),
                      committer_date=first.get("committer_date"), author=first.get("author_name"),
                      identity=first.get("identity"), subject=first.get("subject"),
                      flags=first.get("flags") or [])
    return result


def compare(a, b, files, fragments=(), cfg=None):
    observations = []
    counts = {"A_EARLIER": 0, "B_EARLIER": 0, "SAME_RECORDED_TIME": 0, "UNKNOWN": 0}
    items = [(item, "EXACT_FILE") for item in files[:10]] + [(item, "NORMALIZED_CODE_FRAGMENTS") for item in fragments[:4]]
    for item, kind in items:
        matcher = None
        if kind == "EXACT_FILE":
            digest = a["files"][item["file_a"]]["sha256"]
        else:
            from .similarity import code_tokens, winnow
            wanted = item["fingerprints"]
            digest = hashlib.sha256(str(sorted(wanted)).encode()).hexdigest()
            def matcher(raw, wanted=wanted, ext=Path(item["file_a"]).suffix.lower()):
                try:
                    present = winnow(code_tokens(raw.decode("utf-8"), ext), cfg["code_k_tokens"], cfg["code_window"])
                    return wanted <= set(present)
                except UnicodeDecodeError:
                    return False
        left = observe(a, item["file_a"], digest, matcher)
        right = observe(b, item["file_b"], digest, matcher)
        da, db = date(left.get("committer_date")), date(right.get("committer_date"))
        order = "UNKNOWN"
        if da and db:
            order = "A_EARLIER" if da < db else "B_EARLIER" if db < da else "SAME_RECORDED_TIME"
        counts[order] += 1
        observations.append({"file_a": item["file_a"], "file_b": item["file_b"], "kind": kind,
                             "match_digest": digest, "shared_fingerprints": len(item.get("fingerprints", [])),
                             "a": left, "b": right, "recorded_order": order})
    return {"method": "Exact files and normalized matching-code fragments checked against raw historical Git blobs; ordered by committer date.",
            "counts": counts, "files": observations, "direction": "NOT_ESTABLISHED", "limitation": LIMITATION}
