import json
import logging
import os
import re

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

project_client = AIProjectClient(
    endpoint=os.environ.get("AZURE_EXISTING_AIPROJECT_ENDPOINT"),
    credential=DefaultAzureCredential(),
)
openai_client = project_client.get_openai_client()

# ---------------------------------------------------------------------------
# Agent ID constants — read from .env, defaults match the deployed IDs
# ---------------------------------------------------------------------------
CTOS_AGENT_ID  = os.environ.get("CTOS_AGENT_ID",  "CTOS-Extractor:2")
ERP_AGENT_ID   = os.environ.get("ERP_AGENT_ID",   "Internal-ERP-Agent:2")
BANK_AGENT_ID  = os.environ.get("BANK_AGENT_ID",  "Bank-Statement-Analyst:2")
CHIEF_AGENT_ID = os.environ.get("CHIEF_AGENT_ID", "Chief-Credit-Officer:6")


def call_agent(
    agent_id: str,
    user_message: str,
    expect_json: bool = False,
    images: list[str] | None = None,
):
    """
    Call a pre-deployed Foundry agent.

    Args:
        agent_id:     Foundry agent ID, e.g. "CTOS-Extractor:2".
        user_message: Text payload sent as the user turn.
        expect_json:  Parse the response as a JSON dict.
        images:       Optional list of base64-encoded PNG strings. When provided,
                      the message is sent as multi-part vision content so the
                      agent can perform OCR on scanned PDF pages.
    """
    parts = agent_id.split(":")
    myAgent = parts[0]
    myVersion = parts[1] if len(parts) > 1 else "1"

    # Build content — multi-part when images are present, plain string otherwise
    if images:
        content = [{"type": "input_text", "text": user_message}]
        for b64 in images:
            content.append({
                "type": "input_image",
                "image_url": f"data:image/png;base64,{b64}",
            })
        input_payload = [{"role": "user", "content": content}]
    else:
        input_payload = [{"role": "user", "content": user_message}]

    response = openai_client.responses.create(
        input=input_payload,
        extra_body={"agent_reference": {"name": myAgent, "version": myVersion, "type": "agent_reference"}}
    )

    output_text = getattr(response, 'output_text', str(response))

    if expect_json:
        cleaned = re.sub(r"```(?:json)?\s*([\s\S]*?)```", r"\1", output_text).strip()

        logger.debug("Raw LLM output from %s: %s", agent_id, cleaned[:500])

        return json.loads(cleaned)

    return output_text
