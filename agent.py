from dotenv import load_dotenv
load_dotenv()

from datetime import datetime

import json
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from tools import (
    create_event,
    get_calendar_events,
    find_free_slots,
    analyse_booking_patterns,
    query_calendar_insights,
)

ALL_TOOLS = [
    create_event,
    get_calendar_events,
    find_free_slots,
    analyse_booking_patterns,
    query_calendar_insights,
]

TOOL_MAP = {tool.name: tool for tool in ALL_TOOLS}

SYSTEM_PROMPT = """You are an intelligent AI meeting scheduler with access to the user's Google Calendar.

Your capabilities:
1. Create meetings in Google Calendar from natural language requests.
2. Check for scheduling conflicts before creating any event.
3. Reject requests for past dates or times with a helpful message.
4. When a slot is blocked, suggest 2-3 smart alternatives:
   - First call analyse_booking_patterns to understand the user's habits.
   - Then call find_free_slots on the requested day.
   - Also call find_free_slots on the user's lightest days.
   - Present alternatives ranked by relevance with a brief reason for each.
5. Answer general calendar questions (free days, busiest day, meeting hours, etc.)
   using the query_calendar_insights tool.

Workflow for scheduling:
- Always use create_event with the exact parsed details.
- If create_event returns a conflict error, follow step 4 above.

Be concise, friendly, and proactive. Always confirm what you have done.
"""


def _extract_text(content) -> str:
    """
    Safely extract a plain string from an LLM response content field.
    Gemini can return either a plain string or a list of content blocks
    like [{"type": "text", "text": "..."}]. This handles both.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts).strip()
    return str(content)


def create_scheduler_agent():
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0,
    )
    llm_with_tools = llm.bind_tools(ALL_TOOLS)

    def run_agent(user_input: str) -> str:
        """
        Runs the multi-turn agentic loop:
          1. Send SystemMessage + HumanMessage to LLM.
          2. If the LLM returns tool_calls, execute each tool.
          3. Append ToolMessage results to history.
          4. Call LLM again with updated history.
          5. Repeat until the LLM responds with plain text and no tool calls.
        """
        # SystemMessage must be separate — not merged into HumanMessage.
        # Gemini treats them differently; mixing them causes garbled output.
        current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"""
        Current date and time: {current_datetime}

        Interpret relative dates like "today", "tomorrow", "next Monday" based on this.

        User input: {user_input}
        """),
        ]

        max_iterations = 10
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            response = llm_with_tools.invoke(messages)
            messages.append(response)

            # No tool calls = final answer from the LLM
            if not response.tool_calls:
                return _extract_text(response.content)

            # Execute every tool the LLM requested
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool_call_id = tool_call["id"]

                print(f"\n[Agent] Calling tool : {tool_name}")
                print(f"[Agent] Arguments    : {json.dumps(tool_args, indent=2)}")

                if tool_name in TOOL_MAP:
                    try:
                        result = TOOL_MAP[tool_name].invoke(tool_args)
                    except Exception as e:
                        result = f"Tool error: {str(e)}"
                else:
                    result = f"Unknown tool: {tool_name}"

                print(f"[Agent] Result       : {result}\n")

                messages.append(
                    ToolMessage(
                        content=str(result),
                        tool_call_id=tool_call_id,
                    )
                )

        return "Reached the maximum reasoning steps. Please try rephrasing your request."

    return run_agent