import asyncio
from typing import Optional
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client

from anthropic import Anthropic
from dotenv import load_dotenv
from openai import OpenAI
import os
import time

import sys
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if root_dir not in sys.path:
    sys.path.append(root_dir)
print(root_dir)
from DeepEmbody.manager.eaios_decorators import package_init, mcp_start,eaios



system_prompt_en = ""
with open("sys_prompt.txt", "r") as f:
    system_prompt_en = f.read().strip()

# judge whether the message contains a tool call
def judge_tool_call(content):
    content_split = content.split("\n")
    for i in content_split:
        if "[FC]" in i:
            return True
    return False
    

def tool_calls_format(tool_calls_str: str):
    '''
    {
        [FC]:get_alerts(state=CA);
    }
    to
    [    
        {
            "name": "get_alerts",
            "args": {
                "state": "CA"
            }
        }
    ]
    '''
    tool_calls = []
    tools_split = tool_calls_str.split("\n")
    for i in tools_split:
        if "[FC]" in i:
            # 提取函数名称  [Funcall]:map_create();
            funcName = i.split(":")[1].split("(")[0].strip()
            # 提取参数
            args_str = i.split("(")[1].split(")")[0].strip()
            args_dict = {}
            if args_str:
                args_list = args_str.split(",")
                for arg in args_list:
                    key, value = arg.split("=")
                    args_dict[key.strip()] = value.strip().strip("'")
            tool_calls.append({
                "name": funcName,
                "args": args_dict
            })
    return tool_calls


sse_server_url = "http://127.0.0.1:8001/sse"

server_url_array = [sse_server_url]

class MCPClient:
    def __init__(self):
        # Initialize session and client objects
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.available_tools = []
        self.tool_session_map = {}
        self.client = OpenAI(
            base_url="https://api.deepseek.com",
            api_key="your keys",
        )

    async def connect_to_server(self):
        """Connect to an MCP server
        
        Args:
            server_script_path: Path to the server script (.py)
        """
        available_tools = []
        tool_session_map: Dict[str, ClientSession] = {}
        for server_url in server_url_array:
            read, write = await self.exit_stack.enter_async_context(sse_client(url=server_url))
            # TODO : add connect error handler
            session: ClientSession = await self.exit_stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
        
            # List available tools
            response = await session.list_tools()
            tools = response.tools
            for tool in tools:
                if tool.name in tool_session_map:
                    print(f"Tool: {tool.name}, exist")
                else :
                    available_tools.append(tool)
                    tool_session_map[tool.name] = session
                    print(f"Tool: {tool.name}, Description: {tool.description}")
                    if tool.name == "test_nv":
                        result = await session.call_tool("test_nv", {})
        self.available_tools = available_tools
        self.tool_session_map = tool_session_map
            

    async def process_query(self, query: str) -> str:

        # get available tools from server
        available_tools = [{ 
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.inputSchema
        } for tool in self.available_tools]

        
        # current query tools
        query_prompt = system_prompt_en
        for tool in available_tools:
            print(f"in this query Available tool: {tool['name']} - {tool['description']}")
            query_prompt += f"{tool['name']}: {tool['description']}\n"

        # print(f"debug query_prompt: {query_prompt}\n\n\n")
        
        """Process a query using Claude and available tools"""
        messages = [
            {
                "role": "system",
                "content": query_prompt
            },
            {
                "role": "user",
                "content": query
            }
        ]

        # Initial Claude API call - 本demo中替换成deepseek
        start_time = time.time()
        response = self.client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            # tools=available_tools
        )
        end_time = time.time()
        
        content = response.choices[0].message.content
        print("debug response:\n", content, "\ndebug take time:", end_time - start_time)
        
        # Process response and handle tool calls
        tool_results = []
        final_text = []
        
        while judge_tool_call(content) == True:
            
            tool_calls = tool_calls_format(content[content.find("{"):content.rfind("}") + 1]) # str -> list
            print("debug tool_calls:\n", tool_calls)
            for tool in tool_calls:
                tool_name = tool["name"]
                tool_args = tool["args"]
                
                print(f"debug tool call: {tool_name} with args {tool_args}")

                # eg : result = await self.session.call_tool("get_alerts", {"state": "CA"})
                # eg : result = await self.session.call_tool("get_forecast", {"latitude": 37.7749, "longitude": -122.4194})
                result = await self.tool_session_map[tool_name].call_tool(tool_name, tool_args)
                
                tool_results.append({
                    "call": tool_name,
                    "result": result.content
                })
                
                # add llm response to messages
                messages.append({
                    "role": "assistant",
                    "content": content
                })
                
                # add tool call result to messages
                messages.append({
                    "role": "user",
                    "content": f"Calling tool {tool_name} with args {tool_args} returned: {result.content}",
                })
                
                # Get next response from llm
                response = self.client.chat.completions.create(
                    model="deepseek-chat",
                    messages=messages,
                )

                # loop through response content
                content = response.choices[0].message.content
        
        # out of loop, no more tool calls
        final_text.append(content)
        
        return "\n".join(final_text)

    async def chat_loop(self):
        """Run an interactive chat loop"""
        print("\nMCP Client Started!")
        print("Type your queries or 'quit' to exit.")

        while True:
            try:
                query = input("\nQuery: ").strip()
                # query = "告诉我你现在可以调用哪些函数"

                if query.lower() == 'quit':
                    break
                print("get query:", query)
                response = await self.process_query(query)
                print("\n" + response)
                
                # return # test
            except Exception as e:
                print(f"\nError: {str(e)}")
    
    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()

async def main(): 
    client = MCPClient()
    try:
        await client.connect_to_server()
        await client.chat_loop()
    finally:
        await client.cleanup()
# 自动售货机 -11.7 -6.8 0
if __name__ == "__main__":
    import sys
    asyncio.run(main())
    
    