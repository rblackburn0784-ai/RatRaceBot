def parse_team_ids_csv(team_ids_csv: str, limit: int = 10) -> list[int]:
    ids: list[int] = []
    seen: set[int] = set()

    for raw_id in team_ids_csv.split(","):
        raw_id = raw_id.strip()
        if not raw_id.isdigit():
            continue

        team_id = int(raw_id)
        if team_id in seen:
            continue

        seen.add(team_id)
        ids.append(team_id)
        if len(ids) >= limit:
            break

    return ids
