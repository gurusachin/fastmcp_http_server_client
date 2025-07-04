import asyncio
import json
import time
import uuid
from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from openai import AsyncOpenAI

openai_key = "openai_key"

app = FastAPI()

transport = StreamableHttpTransport("http://127.0.0.1:8000/mcp/")
mcp_client: Optional[Client] = None

sessions: dict[str, 'ChatSession'] = {}

SYSTEM_PROMPT = """
You are a highly capable assistant with access to external tools via function calls.

Your responsibilities:

- Plan clearly and step by step.
- Generate the content for the mandatory fields in the tool schema needed
- After calling the tool, check if further steps are needed to fully satisfy the request.
- based on the prompt fill the mandatory fields yourself.

**Rules**:

- Use optional data if available.
- Plan iteratively but limit the number of iterations to avoid loops.
"""


class ChatSession:
    def __init__(self, session_id: str, available_tools: list):
        self.session_id = session_id
        self.available_tools = available_tools
        self.messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
        ]
        self.last_activity = time.time()

    def append_user_message(self, user_content: str):
        self.messages.append({
            "role": "user",
            "content": user_content + "\n Please call necessary APIs/tools needed"
        })
        self.update_activity()

    def append_assistant_message(self, assistant_content: str):
        self.messages.append({
            "role": "assistant",
            "content": assistant_content
        })
        self.update_activity()

    def update_activity(self):
        self.last_activity = time.time()


@app.on_event("startup")
async def startup():
    global mcp_client
    mcp_client = Client(transport=transport)
    await mcp_client.__aenter__()
    await mcp_client.ping()
    print("✅ MCP client is ready!")
    asyncio.create_task(session_cleanup_task())


@app.on_event("shutdown")
async def shutdown():
    if mcp_client:
        await mcp_client.__aexit__(None, None, None)


async def create_session() -> ChatSession:
    tools = await mcp_client.list_tools()
    session_id = str(uuid.uuid4())
    session = ChatSession(session_id, [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema
            }
        } for tool in tools
    ])
    sessions[session_id] = session
    print(f"🆕 Created new session: {session_id}")
    return session


def get_session(session_id: str) -> Optional[ChatSession]:
    return sessions.get(session_id)


async def session_cleanup_task():
    while True:
        await asyncio.sleep(60)
        now = time.time()
        expired = [
            sid for sid, s in sessions.items()
            if now - s.last_activity > 3600
        ]
        for sid in expired:
            print(f"🗑️  Cleaning up idle session: {sid}")
            del sessions[sid]


class MCP_ChatBot:

    def __init__(self, session: ChatSession, max_iterations: int = 5):
        self.session = session
        self.max_iterations = max_iterations
        self.openAIClient = AsyncOpenAI(api_key=openai_key)

    async def process_query(self):
        for iteration in range(self.max_iterations):
            print(f"🔁 Planning iteration: {iteration + 1}/{self.max_iterations}")

            completion = await self.openAIClient.chat.completions.create(
                model="gpt-4o-mini",
                messages=self.session.messages,
                tools=self.session.available_tools,
                temperature=0.2
            )

            message = completion.choices[0].message
            print("message.tool_calls:: ",message.tool_calls)
            if message.tool_calls:
                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)

                    print(f"🔧 Calling tool {tool_name} with args {tool_args}")

                    result = await mcp_client.call_tool(tool_name, arguments=tool_args)
                    result_text = "\n".join(
                        block.text for block in result if block.type == "text"
                    )

                    self.session.append_user_message(
                        f"Result of calling {tool_name}:\n{result_text}"
                    )
                continue

            assistant_raw_reply = message.content
            print(f"🧩 Raw assistant reply: {assistant_raw_reply}")

            self.session.append_assistant_message(assistant_raw_reply)

            try:
                parsed = json.loads(assistant_raw_reply)
                msg_type = parsed.get("type")
                msg_content = parsed.get("content")
            except json.JSONDecodeError:
                print("❗ Assistant did not return valid JSON. Returning raw text.")
                return assistant_raw_reply

            if msg_type == "followup":
                print(f"❓ Assistant followup: {msg_content}")
                return msg_content

            elif msg_type == "final_answer":
                print(f"✅ Assistant final answer: {msg_content}")
                if isinstance(msg_content, str):
                    return msg_content
                else:
                    return json.dumps(msg_content, ensure_ascii=False)

            else:
                print("❗ Unexpected 'type' value in assistant response.")
                return msg_content or assistant_raw_reply

        return "⚠️ Max planning iterations reached. Please refine your request."


class ChatRequest(BaseModel):
    user_message: str
    session_id: Optional[str] = None
    max_iterations: Optional[int] = 5


class ChatResponse(BaseModel):
    session_id: str
    answer: str


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    session = None

    if request.session_id:
        session = get_session(request.session_id)
        if not session:
            return ChatResponse(
                session_id="",
                answer="❗ Invalid session ID. Please start a new session."
            )

    if not session:
        session = await create_session()

    session.append_user_message(request.user_message)

    chatbot = MCP_ChatBot(session, max_iterations=request.max_iterations or 5)
    answer = await chatbot.process_query()

    return ChatResponse(
        session_id=session.session_id,
        answer=answer
    )
