from ..State import AgentState
from ..tools import read_file_numbered,list_folder_content
from langchain_deepseek import ChatDeepSeek
from langchain.agents import create_agent
from dotenv import load_dotenv
load_dotenv()
tools = [read_file_numbered,list_folder_content]

llm = ChatDeepSeek(model="deepseek-chat")

agent = create_agent(llm,tools=tools)

def Diagnose(state:AgentState) -> AgentState:
    prompt = f"""You are a senior software developer is there is the following issue you have 
                 issue_title: {state["issue_title"]},
                 issue_description: {state["issue_description"]},
                 from the issue recommend the files and folder that need to be changed 
                 and then read these files and give the diagnose on the sitation like what needs to be changed and what do you recommend
                 we do not need you to change the code only diagnosis tell us what is wrong and in what files"""
    inputs = {
        "messages": [
            ("user", prompt)
        ]
    }

    # FIX 2: Invoke the agent with the state dictionary
    response = agent.invoke(inputs)

    # FIX 3: Extract the final answer from the last message in the returned state
    final_answer = response["messages"][-1].content

    return {"Diagnose": final_answer}
