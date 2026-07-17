# AGENTS — Developer Helper MCP

**Mission:** Get a coding agent + human to a **first green** Zeus Client app turn.

## Load order

1. This file  
2. [koten_docs agent-index.yaml](https://github.com/koten-ai/koten_docs/blob/zeus-v1.0.0/agent-index.yaml)  
3. [for-ai-agents.md](https://github.com/koten-ai/koten_docs/blob/zeus-v1.0.0/zeus-client/for-ai-agents.md)  
4. [using-zeus-client.md](https://github.com/koten-ai/koten_docs/blob/zeus-v1.0.0/zeus-client/using-zeus-client.md)  
5. [zeus_chat_request](https://github.com/koten-ai/zeus_chat_request) for templates  

## Hard constraints

- Public API **:8080** only (never Hub **:9091** from app path)  
- Never invent `contract_hash`  
- Catalogs: live stamp preferred; `fetch_chat_request` is **template only**  
- No secrets in tool results or checklist evidence  

## Tools to use first

`doctor` → `start_project` → `list_catalog_modes` → `fetch_chat_request` → `explain` → `next_step`

## Not this MCP

Data-plane tools, Hub admin mutations, multi-agent jobs (ZJA).
