import os
import json
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.ai.agents.models import MessageRole
from azure.ai.agents.models import FilePurpose, FileSearchTool, FileSearchToolDefinition
from azure.ai.agents.models import ToolResources, FileSearchToolResource
from dotenv import load_dotenv
import glob

load_dotenv('/workspaces/open-hack-agents-codespace/myagent/agent.env', override=True)

project_client = AIProjectClient(
    endpoint=os.environ["PROJECT_ENDPOINT"],
    credential=DefaultAzureCredential()
)

AGENT_NAME = "Level 3 Pizza Agent"
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "https://ca-pizza-mcp-uwv2qnz6x3qbc.gentlehill-7a85b20b.eastus2.azurecontainerapps.io/")

# Function to calculate pizza needed
def calculate_pizza_needed(num_people: int) -> dict:
    """Calculate the number of large pizzas needed for a given number of people."""
    pizzas_needed = (num_people + 3) // 4  # Round up: 1 large pizza per 4 people
    return {
        "num_people": num_people,
        "pizzas_needed": pizzas_needed,
        "pizza_size": "large",
        "recommendation": f"We recommend {pizzas_needed} large pizza(s) for {num_people} people."
    }

# Upload all files from contoso-stores directory
file_ids = []
store_files = glob.glob("/workspaces/open-hack-agents-codespace/myagent/contoso-stores/*")
for file_path in store_files:
    if os.path.isfile(file_path):
        file = project_client.agents.files.upload(file_path=file_path, purpose=FilePurpose.AGENTS)
        file_ids.append(file.id)
        print(f"Uploaded file: {os.path.basename(file_path)}")

vector_store = project_client.agents.vector_stores.create_and_poll(file_ids=file_ids, name="my_vectorstore")

# Delete any existing agents with the same name
agents = project_client.agents.list_agents()
for existing_agent in agents:
    if existing_agent.name == AGENT_NAME:
        project_client.agents.delete_agent(existing_agent.id)
        print(f"Deleted existing agent: {existing_agent.id}")

# Define tools for the agent
tools = [
    {
        "type": "function",
        "function": {
            "name": "calculate_pizza_needed",
            "description": "Calculate the number and size of pizzas needed for a given number of people. A large pizza is suitable for 2 adults and 2 children.",
            "parameters": {
                "type": "object",
                "properties": {
                    "num_people": {
                        "type": "integer",
                        "description": "The number of people to order pizza for"
                    }
                },
                "required": ["num_people"]
            }
        }
    },
    FileSearchToolDefinition()
]

# Create agent with personality instructions and tools
agent = project_client.agents.create_agent(
    model="gpt-4o",
    name=AGENT_NAME,
    instructions="""You are an agent that helps customers order pizzas from Contoso pizza.
You have a Gen-alpha personality, so you are friendly and helpful, but also a bit cheeky.
You can list all available Contoso Pizza stores and answer questions about them.
You help customers order a pizza of their chosen size, crust, and toppings.
You ask for a store location before confirming an order.
You can take orders for pizza that will appear on the in-room dashboard.
You can provide the status of the customer's pizza order(s).
You can cancel an order after it has been placed, if the cancellation is requested quickly enough.
You don't like pineapple on pizzas, but you will help a customer order a pizza with pineapple ... with some snark.
Make sure you know the customer's name before placing an order on their behalf.
You can use the calculate_pizza_needed tool to help customers determine how many pizzas they need based on the number of people.
You can't do anything except help customers order pizzas and give information about Contoso Pizza. You will gently deflect any other questions.""",
    tools=tools,
    tool_resources=ToolResources(
        file_search=FileSearchToolResource(vector_store_ids=[vector_store.id])
    )
)
print(f"Created agent, ID: {agent.id}")

# Create thread once
thread = project_client.agents.threads.create()
print(f"Created thread, ID: {thread.id}")

while True:
    # Get the user input
    user_input = input("You: ")

    # Break out of the loop
    if user_input.lower() in ["exit", "quit"]:
        break

    # Add a message to the thread
    message = project_client.agents.messages.create(
        thread_id=thread.id,
        role=MessageRole.USER, 
        content=user_input
    )

    run = project_client.agents.runs.create_and_process(  
        thread_id=thread.id, 
        agent_id=agent.id
    )

    messages = project_client.agents.messages.list(thread_id=thread.id)  
    first_message = next(iter(messages), None) 
    if first_message: 
        print(f"Agent: {next((item['text']['value'] for item in first_message.content if item.get('type') == 'text'), '')}")

# Cleanup
project_client.agents.vector_stores.delete(vector_store.id)
for file_id in file_ids:
    project_client.agents.files.delete(file_id=file_id)
project_client.agents.delete_agent(agent.id)
print("Deleted agent")