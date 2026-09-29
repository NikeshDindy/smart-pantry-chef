"""Minimal FastAPI proxy for a deployed A2A agent (Agent Runtime, agents-cli 1.1.0+).

The browser talks ONLY to this proxy (same origin, no CORS, no GCP creds in the
browser). The proxy authenticates with Application Default Credentials and
forwards chat to the deployed agent over the A2A protocol, returning replies as
structured parts the chat UI knows how to show:

  * {"kind": "text", "text": ...}  -> a normal chat bubble
  * {"kind": "a2ui", "data": ...}  -> one A2UI message (beginRendering /
    surfaceUpdate); static/index.html renders these as a card.

Why A2A: agents-cli 1.1.0 (GA) deploys ADK agents to Agent Runtime as A2A agents
and no longer registers the reasoning-engine operation schema the old
`agent_engines.get(...).stream_query()` path relied on (operation_schemas() comes
back empty). The container serves the A2A protocol over the Agent Engine HTTP
passthrough, so this proxy fetches the agent's card and sends messages with the
a2a-sdk client (the same path `agents-cli run --mode a2a` uses). This works for
both A2A and plain ADK 1.1.0 deployments (the container serves A2A either way).

Run:
  pip install -r requirements.txt
  export AGENT_ENGINE_RESOURCE_NAME="projects/.../locations/.../reasoningEngines/..."
  export AGENT_DIRECTORY="app"   # your agent's app directory (agents-cli-manifest.yaml)
  python main.py                 # -> http://localhost:8080
"""

import os
import uuid

import google.auth
import google.auth.transport.requests
import httpx
from a2a.client import ClientConfig, ClientFactory
from a2a.types import (
    AgentCard,
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
)

try:
    from a2a.types import TextPart, FilePart
except ImportError:
    TextPart = None
    FilePart = None

try:
    from a2a.types import TransportProtocol
except ImportError:
    TransportProtocol = None

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

RESOURCE = os.environ["AGENT_ENGINE_RESOURCE_NAME"]
# The agent's app directory (matches agent_directory in agents-cli-manifest.yaml).
AGENT_DIRECTORY = os.environ.get("AGENT_DIRECTORY", "app")
# Location is embedded in the resource name: projects/<p>/locations/<loc>/reasoningEngines/<id>.
LOCATION = RESOURCE.split("/locations/")[1].split("/")[0]

# A2A endpoint for an Agent Runtime deployment, via the Agent Engine HTTP
# passthrough. The card lives at the well-known path under this base.
A2A_BASE = (
    f"https://{LOCATION}-aiplatform.googleapis.com/reasoningEngines/v1/"
    f"{RESOURCE}/api/a2a/{AGENT_DIRECTORY}"
)
A2A_CARD_URL = f"{A2A_BASE}/.well-known/agent-card.json"

# The agent tags its A2UI data parts with this mime type.
_A2UI_MIME = "application/json+a2ui"

# One set of ADC credentials, refreshed per request (access tokens expire ~1h).
_creds, _ = google.auth.default(
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)


def _auth_headers() -> dict[str, str]:
    _creds.refresh(google.auth.transport.requests.Request())
    return {
        "Authorization": f"Bearer {_creds.token}",
        "Content-Type": "application/json",
    }


app = FastAPI()


@app.exception_handler(Exception)
async def _json_errors(request: Request, exc: Exception):
    # Always return JSON so the browser never receives a plain-text 500 page
    # (which shows up in the chat as "Unexpected token 'I', "Internal S"... is
    # not valid JSON"). Any server-side failure now surfaces as a readable
    # message in the chat bubble instead.
    return JSONResponse(
        status_code=200,
        content={
            "parts": [{"kind": "text", "text": f"Error: {type(exc).__name__}: {exc}"}]
        },
    )


# Reuse ONE A2A context per user so the agent remembers the conversation.
_contexts: dict[str, str] = {}
# Cache the agent card after the first fetch.
_card = None

try:
    from a2a.client import A2ACardResolver
except ImportError:
    A2ACardResolver = None


try:
    from a2a.types import SendMessageRequest
except ImportError:
    SendMessageRequest = None


async def _get_card(client: httpx.AsyncClient) -> AgentCard:
    global _card
    if _card is None:
        if A2ACardResolver is not None:
            resolver = A2ACardResolver(base_url=A2A_BASE, httpx_client=client)
            _card = await resolver.get_agent_card()
        else:
            resp = await client.get(A2A_CARD_URL)
            resp.raise_for_status()
            card_data = resp.json()
            card = AgentCard(**card_data) if isinstance(card_data, dict) else card_data
            card.url = A2A_BASE
            _card = card
    return _card


def _extract_parts(parts: list) -> list[dict]:
    """Turn A2A response parts into structured parts for the chat UI."""
    from google.protobuf.json_format import MessageToDict
    import base64, re, json

    out: list[dict] = []
    for p in parts:
        d = None
        if hasattr(p, "DESCRIPTOR"):
            try:
                d = MessageToDict(p)
            except Exception as e:
                print("MessageToDict error:", e)
        elif isinstance(p, dict):
            d = p
        elif isinstance(p, str) and p:
            out.append({"kind": "text", "text": p})
            continue

        if not isinstance(d, dict):
            continue

        # 1. Text field
        text = d.get("text")
        if isinstance(text, str) and text:
            if "<a2a_datapart_json>" in text:
                matches = re.findall(r"<a2a_datapart_json>(.*?)</a2a_datapart_json>", text, re.DOTALL)
                for m in matches:
                    try:
                        parsed = json.loads(m.strip())
                        payload = parsed.get("data") if isinstance(parsed, dict) and "data" in parsed else parsed
                        if payload:
                            out.append({"kind": "a2ui", "data": payload})
                    except Exception:
                        pass
                if out:
                    continue
            out.append({"kind": "text", "text": text})
            continue

        # 2. Inline data field (b64 encoded in MessageToDict)
        inline_data = d.get("inlineData") or d.get("inline_data")
        if isinstance(inline_data, dict):
            raw = inline_data.get("data", "")
            if isinstance(raw, str):
                try:
                    decoded = base64.b64decode(raw).decode("utf-8", errors="ignore")
                except Exception:
                    decoded = raw
                if "<a2a_datapart_json>" in decoded:
                    matches = re.findall(r"<a2a_datapart_json>(.*?)</a2a_datapart_json>", decoded, re.DOTALL)
                    for m in matches:
                        try:
                            parsed = json.loads(m.strip())
                            payload = parsed.get("data") if isinstance(parsed, dict) and "data" in parsed else parsed
                            if payload:
                                out.append({"kind": "a2ui", "data": payload})
                        except Exception:
                            pass
                    if out:
                        continue
                elif decoded and not decoded.startswith("<"):
                    out.append({"kind": "text", "text": decoded})
                    continue

        # 3. Data field (Struct dictionary, e.g. A2UI data parts)
        data = d.get("data")
        if isinstance(data, dict):
            meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
            mime = meta.get("mimeType")
            inner = data.get("data") if "data" in data and isinstance(data["data"], dict) else data

            if mime == _A2UI_MIME or (isinstance(inner, dict) and any(k in inner for k in ("beginRendering", "surfaceUpdate", "dataModelUpdate"))):
                out.append({"kind": "a2ui", "data": inner})
                continue

    return out


@app.post("/chat")
async def chat(req: Request):
    body = await req.json()
    message = body.get("message", "")
    user_id = body.get("user_id") or "web-user"
    parts: list[dict] = []

    async with httpx.AsyncClient(headers=_auth_headers(), timeout=120) as client:
        card = await _get_card(client)
        config_kwargs = {"httpx_client": client}
        if TransportProtocol is not None:
            config_kwargs["supported_transports"] = [
                getattr(TransportProtocol, "jsonrpc", "jsonrpc"),
                getattr(TransportProtocol, "http_json", "http_json"),
            ]
        factory = ClientFactory(ClientConfig(**config_kwargs))
        a2a_client = factory.create(card)

        part_root = TextPart(text=message) if TextPart is not None else message
        part_obj = Part(root=part_root) if hasattr(Part, "root") else Part(text=message)
        role_val = Role.user if hasattr(Role, "user") else getattr(Role, "ROLE_USER", "user")

        msg = Message(
            message_id=str(uuid.uuid4()),
            role=role_val,
            parts=[part_obj],
            context_id=_contexts.get(user_id) or "",
        )

        send_req = SendMessageRequest(message=msg) if SendMessageRequest is not None else msg

        last_task = None
        got_artifact_update = False
        async for event in a2a_client.send_message(send_req):
            print("A2A EVENT:", type(event), event)
            if getattr(event, "HasField", None):
                if event.HasField("task"):
                    last_task = event.task
                    if getattr(event.task, "context_id", None):
                        _contexts[user_id] = event.task.context_id
                if event.HasField("artifact_update"):
                    extracted = _extract_parts(event.artifact_update.artifact.parts)
                    if extracted:
                        got_artifact_update = True
                        parts.extend(extracted)
                if event.HasField("status_update"):
                    st = event.status_update.status
                    if st.HasField("message"):
                        msg_parts = _extract_parts(st.message.parts)
                        if msg_parts:
                            parts.extend(msg_parts)
            elif isinstance(event, tuple):
                task, update = event
                if task is not None:
                    last_task = task
                    if getattr(task, "context_id", None):
                        _contexts[user_id] = task.context_id
                if isinstance(update, TaskArtifactUpdateEvent):
                    extracted = _extract_parts(update.artifact.parts)
                    if extracted:
                        got_artifact_update = True
                        parts.extend(extracted)

        # Fallback 1: pull parts from final task's artifacts
        if not parts and last_task is not None:
            for artifact in getattr(last_task, "artifacts", None) or []:
                parts.extend(_extract_parts(artifact.parts))

        # Fallback 2: pull parts from final task's history (agent messages only)
        if not parts and last_task is not None:
            user_role_vals = {1, "1", "user", "role_user", "ROLE_USER"}
            if hasattr(Role, "ROLE_USER"):
                user_role_vals.add(getattr(Role, "ROLE_USER"))
            if hasattr(Role, "user"):
                user_role_vals.add(getattr(Role, "user"))

            for hist in getattr(last_task, "history", None) or []:
                role = getattr(hist, "role", None)
                if role not in user_role_vals and str(role).lower() not in user_role_vals:
                    if hasattr(hist, "parts"):
                        parts.extend(_extract_parts(hist.parts))

    if not parts:
        parts = [{"kind": "text", "text": "(The agent didn't return a reply.)"}]
    print("CHAT RETURN PARTS COUNT:", len(parts), "PARTS:", parts)
    return JSONResponse({"parts": parts})




# Serve the chat UI (keep this mount last so /chat wins).
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
