"""Scout: pull new jobs from the marketplace, drop duplicates, return the ones worth analysing.
Dedup key = normalised title + client. A repost ("(repost)" suffix, different id) gets the same key."""
import re

NS = "seen_jobs"


def fingerprint(job: dict) -> str:
    title = re.sub(r"\(repost\)|\brepost\b", "", job["title"], flags=re.I)
    title = re.sub(r"[^a-z0-9 ]", "", title.lower())
    return f"{job['client_id']}|{' '.join(title.split())}"


async def scout(store, persona: str, jobs: list[dict]) -> dict:
    """Returns {'new': [...], 'duplicates': [{'job_id', 'duplicate_of'}]}. Idempotent: calling twice
    with the same jobs queues each only once, so a worker restart never double-processes."""
    new, dups = [], []
    for j in jobs:
        fp = fingerprint(j)
        hit = await store.aget((persona, NS), fp)
        if hit and hit.value["job_id"] != j["job_id"]:
            dups.append(dict(job_id=j["job_id"], duplicate_of=hit.value["job_id"]))
        elif not hit:
            await store.aput((persona, NS), fp, {"job_id": j["job_id"]})
            new.append(j)
        # same job_id seen again: already queued, skip silently
    return {"new": new, "duplicates": dups}