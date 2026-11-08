"""Buffer GraphQL client: channels, createPost (customScheduled) and sent posts.

Modelled on AIREP's marketing/buffer.py. The API key never appears in a log line,
an exception message or a return value; keep it that way when adding code here.
"""

from __future__ import annotations

from typing import Any

import requests

ENDPOINT = "https://api.buffer.com"
TIMEOUT_SECONDS = 30

# Two steps, as the API docs show them. The one-shot form that nested `channels` under
# `account.organizations` is answered with "Not authorized to access this resource" for
# a personal key that can read channels perfectly well through `channels(input:)`
# (live 2026-11-08, the AIREP key).
LIST_ORGANIZATIONS_QUERY = """
query {
  account {
    id
    organizations { id name }
  }
}
"""

LIST_CHANNELS_QUERY = """
query Channels($id: OrganizationId!) {
  channels(input: { organizationId: $id }) { id service name displayName isDisconnected }
}
"""

# createPost returns the PostActionPayload UNION: a bare `id` selection 400s, so the
# success and error members are read through inline fragments (AIREP hit this in prod).
CREATE_POST_MUTATION = """
mutation CreatePost($input: CreatePostInput!) {
  createPost(input: $input) {
    __typename
    ... on PostActionSuccess { post { id dueAt } }
    ... on MutationError { message }
  }
}
"""

# Read-only helper for the legacy import: which captions already ran on each page.
# PostSortInput's exact shape is unverified; the query fails loudly if it is wrong.
SENT_POSTS_QUERY = """
query SentPosts($input: PostsInput!, $first: Int) {
  posts(input: $input, first: $first) {
    edges { node { id text dueAt status channel { id service } } }
  }
}
"""

# Facebook rejects a post without a type; LinkedIn needs none (AIREP's finding).
SERVICE_POST_TYPE = {"facebook": "post"}


class BufferError(Exception):
    """A transport, HTTP or GraphQL failure; the message is safe to print."""


def _post_graphql(token: str, payload: dict[str, Any]) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        response = requests.post(ENDPOINT, json=payload, headers=headers, timeout=TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise BufferError(f"Buffer transport error: {exc}") from exc
    if response.status_code >= 400:
        raise BufferError(f"Buffer HTTP {response.status_code}: {response.text[:500]}")
    try:
        body = response.json()
    except ValueError as exc:
        raise BufferError(f"Buffer returned non-JSON: {response.text[:200]}") from exc
    errors = body.get("errors") if isinstance(body, dict) else None
    if errors:
        joined = "; ".join(str(e.get("message", "")) for e in errors if isinstance(e, dict))
        raise BufferError(f"Buffer GraphQL error: {joined or 'unknown'}")
    return body


def list_channels(token: str) -> list[dict[str, Any]]:
    """Every channel the key can see, flattened: id, service, name, org id, isDisconnected."""
    body = _post_graphql(token, {"query": LIST_ORGANIZATIONS_QUERY})
    account = ((body.get("data") or {}).get("account")) or {}
    flat: list[dict[str, Any]] = []
    for org in account.get("organizations") or []:
        org_body = _post_graphql(
            token, {"query": LIST_CHANNELS_QUERY, "variables": {"id": org.get("id", "")}}
        )
        for channel in (org_body.get("data") or {}).get("channels") or []:
            flat.append(
                {
                    "id": channel.get("id", ""),
                    "service": channel.get("service", ""),
                    "name": channel.get("displayName") or channel.get("name", ""),
                    "organization_id": org.get("id", ""),
                    "isDisconnected": bool(channel.get("isDisconnected", False)),
                }
            )
    return flat


def build_create_input(
    channel_id: str,
    service: str,
    text: str,
    asset_url: str,
    due_at_iso: str,
    *,
    is_video: bool = False,
    alt_text: str = "",
    thumbnail_offset_ms: int | None = None,
) -> dict[str, Any]:
    """The CreatePostInput for one channel; pure, so the dry run can print it."""
    if is_video:
        video: dict[str, Any] = {"url": asset_url}
        # Networks refuse custom video thumbnails (thumbnailUrl is rejected by the
        # API); the frame is chosen by offset where the network supports it.
        if thumbnail_offset_ms is not None:
            video["metadata"] = {"thumbnailOffset": int(thumbnail_offset_ms)}
        asset: dict[str, Any] = {"video": video}
    else:
        image: dict[str, Any] = {"url": asset_url}
        if alt_text:
            image["metadata"] = {"altText": alt_text}
        asset = {"image": image}
    payload: dict[str, Any] = {
        "channelId": channel_id,
        "text": text,
        "assets": [asset],
        "mode": "customScheduled",
        "dueAt": due_at_iso,
        "schedulingType": "automatic",
        "needsApproval": False,
        "source": "airep-social",
    }
    post_type = SERVICE_POST_TYPE.get(service)
    if post_type:
        payload["metadata"] = {service: {"type": post_type}}
    return payload


def create_post(token: str, create_input: dict[str, Any]) -> str:
    """Run createPost and return the new post id; raises BufferError on any failure."""
    body = _post_graphql(
        token, {"query": CREATE_POST_MUTATION, "variables": {"input": create_input}}
    )
    created = ((body.get("data") or {}).get("createPost")) or {}
    typename = created.get("__typename")
    if typename and typename != "PostActionSuccess":
        message = created.get("message") or f"createPost returned {typename}"
        raise BufferError(f"Buffer createPost failed: {message}")
    post_id = (created.get("post") or {}).get("id")
    if not post_id:
        raise BufferError("Buffer createPost returned no post id")
    return str(post_id)


def sent_posts(
    token: str, organization_id: str, channel_ids: list[str], first: int = 100
) -> list[dict[str, Any]]:
    """Posts already published on *channel_ids*, newest first (best effort)."""
    variables = {
        "input": {
            "organizationId": organization_id,
            "filter": {"status": ["sent"], "channelIds": channel_ids},
            "sort": [{"field": "dueAt", "direction": "desc"}],
        },
        "first": first,
    }
    body = _post_graphql(token, {"query": SENT_POSTS_QUERY, "variables": variables})
    edges = (((body.get("data") or {}).get("posts")) or {}).get("edges") or []
    return [edge.get("node") or {} for edge in edges]
