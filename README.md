FASTMCP BASED MCP SERVER AND CLIENT WITH TRANSPORT AS STREAMBALE-HTTP

MCP server converts OAS-spec jsons to MCP servers

PreRequisites:
**To install uv:**
curl -LsSf https://astral.sh/uv/install.sh | sh

1. Clone this repo 
2. cd Repo
3. Setup a venv using uv
   ```uv venv```
   ``` source .venv/bin/activate ```
4. install dependecies ```uv add "mcp[cli]" httpx```


**for running server :**
 uv run main.py 

**for running client :** 
uvicorn mcp_client_session:app --reload --port 9000

**for running inspector :** 
npx @modelcontextprotocol/inspector
 
Note: while running inspector: copy the session id from the terminal output in the configuration input. Leave other things as it is.

Note: While using MCP server - get your access token and paste it in the file
Note: While using MCP client - paste your openAI- API key
