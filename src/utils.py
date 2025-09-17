import os
from datetime import datetime
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from langchain_core.tools import tool
from tools.google_search_tool_serper import google_search_tool
from langchain.agents import AgentExecutor
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents.output_parsers.openai_tools import OpenAIToolsAgentOutputParser
from langchain.agents.format_scratchpad.openai_tools import format_to_openai_tool_messages


# Set the scopes for Google API
SCOPES = [
    # For using GMAIL API
    'https://www.googleapis.com/auth/gmail.modify',
    # For using Google sheets as CRM, can comment if using Airtable or other CRM
    'https://www.googleapis.com/auth/spreadsheets',
    # For saving files into Google Docs
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive"
]

tools = [google_search_tool]

def get_current_date():
    return datetime.now().strftime("%Y-%m-%d")

def get_google_credentials():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return creds
    
def get_report(reports, report_name: str):
    """
    Retrieves the content of a report by its title.
    """
    for report in reports:
        if report.title == report_name:
            return report.content
    return ""

def save_reports_locally(reports):
    # Define the local folder path
    reports_folder = "reports"
    
    # Create folder if it does not exist
    if not os.path.exists(reports_folder):
        os.makedirs(reports_folder)
    
    # Save each report as a file in the folder
    for report in reports:
        file_path = os.path.join(reports_folder, f"{report.title}.txt")
        with open(file_path, "w", encoding="utf-8") as file:
            file.write(report.content)

def get_llm_by_provider(llm_provider, model, tools=None, agent_prompt: str | None = None):
    # Falls keine Tools übergeben wurden, verwende die modulweite Standardliste
    tool_list = tools if tools is not None else globals().get("tools", [])
    # Else find provider
    if llm_provider == "openai":
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(model=model, temperature=1)
    elif llm_provider == "openai-agent":
        from langchain_openai import ChatOpenAI
        # Baue einen Tool-Calling-Agent manuell (ohne prebuilt create_react_agent)
        # 1) Prompt mit Scratchpad
        prompt = ChatPromptTemplate.from_messages([
            ("system", agent_prompt or ""),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

        # 2) LLM an Tools binden
        llm = ChatOpenAI(model=model, temperature=0.1).bind_tools(tool_list)

        # 3) Agent-Pipeline zusammensetzen: input + scratchpad -> prompt -> llm -> parser
        agent = (
            {
                "input": lambda x: x.get("input", ""),
                "agent_scratchpad": lambda x: format_to_openai_tool_messages(x.get("intermediate_steps", [])),
            }
            | prompt
            | llm
            | OpenAIToolsAgentOutputParser()
        )

        # 4) AgentExecutor zurückgeben (von invoke_llm erkannt)
        executor = AgentExecutor(agent=agent, tools=tool_list, verbose=False)
        return executor
    elif llm_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        llm = ChatAnthropic(model=model, temperature=0.1)  # Use the correct model name
    elif llm_provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(model=model, temperature=0.1)  # Correct model name
    # ... add elif blocks for other providers ...
    else:
        raise ValueError(f"Unsupported LLM provider: {llm_provider}")
    return llm

def invoke_llm(
    system_prompt,
    user_message,
    model="gemini-1.5-flash",  # Specify the model name according to the provider
    llm_provider="google",  # By default use Google as provider
    response_format=None):
    # Get base LLM oder AgentExecutor abhängig vom Provider/Einstellung
    # Wenn ReAct-Agent: setze den system_prompt als Agent-Systemkontext
    agent_prompt = system_prompt if llm_provider == "openai-agent" else None
    llm_or_agent = get_llm_by_provider(llm_provider, model, tools=tools, agent_prompt=agent_prompt)

    # Falls ein ReAct-Agent konfiguriert ist
    if isinstance(llm_or_agent, AgentExecutor):
        # Nutze die user_message als Human-Input; system_prompt ist bereits im Agenten gesetzt
        input_text = f"{user_message}"
        result = llm_or_agent.invoke({"input": input_text})
        # AgentExecutor liefert i. d. R. ein Dict mit Schlüssel 'output'
        return result.get("output", str(result))

    # Regulärer LLM-Pfad
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]

    llm_chain = llm_or_agent
    if response_format:
        llm_chain = llm_chain.with_structured_output(response_format)
    else:
        llm_chain = llm_chain | StrOutputParser()

    return llm_chain.invoke(messages)