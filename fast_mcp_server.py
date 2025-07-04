import httpx
import asyncio
import requests
import json
import uvicorn
from fastmcp import FastMCP
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():   
    main_mcp = FastMCP(name="MainApp")
    folder_path = 'oas_files'

    # Create ONE httpx.AsyncClient to use everywhere
    headers = {
        "Authorization": "Bearer {{ACCESS_TOKEN}}"
    }

    async with httpx.AsyncClient(base_url="https://crm.zoho.com", headers=headers) as http_client:
        for filename in os.listdir(folder_path):
            file_path = os.path.join(folder_path, filename)
            print("entering filepath", filename)
            if os.path.isfile(file_path):
                print("creating mcp server with prefix", filename)
                mcp_child = await get_mcp_server(file_path, http_client)
                await main_mcp.import_server(mcp_child, prefix="")    

        await main_mcp.run_async(transport="http")


async def get_mcp_server(json_path, http_client):
    print("file_path", json_path)
    with open(json_path, "r") as f:
        openapi_spec = json.load(f)

    logger.info("Creating FastMCP server from OpenAPI spec")
    fastmcp_api = FastMCP.from_openapi(openapi_spec=openapi_spec, client=http_client)
    return fastmcp_api


if __name__ == "__main__":
    asyncio.run(main())
