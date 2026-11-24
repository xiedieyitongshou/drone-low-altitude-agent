def versioned_task_payload(client, task_id, headers, payload=None):
    """Serial regression setup: act on the task version the client just read.

    Conflict tests deliberately send captured/stale versions without this helper.
    A caller without read permission still reaches the write authorization check.
    """
    response = client.get(f"/tasks/{task_id}", headers=headers)
    version = response.json()["version"] if response.status_code == 200 else 1
    return {"expected_version": version, **(payload or {})}
