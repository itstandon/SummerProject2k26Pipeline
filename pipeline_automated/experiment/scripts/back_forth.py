import os
import json
import re
import datetime
from dotenv import load_dotenv
from pymongo import MongoClient

# Import LLM1 caller and models list
from call_llm import call_llm, MODELS

load_dotenv()

# Configuration
MONGO_URL_OUTPUTS = os.getenv("MONGO_URL_OUTPUTS", "<moengo_url_for_oputputs>")
LLM2_MODEL = os.getenv("LLM2_MODEL", "gpt-4o")
LLM2_API_KEY = os.getenv("LLM2_API_KEY") or os.getenv("OPENAI_API_KEY")

# Choose SOTA model (LLM2) rationale:
# GPT-4o / Gemini 1.5 Pro are chosen as SOTA models due to their advanced reasoning,
# formal methods analysis, massive context windows, and excellent instruction-following capabilities,
# making them perfect for multi-turn principal QA engineering evaluations.

# Define Evaluation Metrics
METRICS = {
    "Requirements Coverage": "Does the generated test case set verify all clauses (privileges, startup/shutdown procedures, access allocation, and deadlock avoidance if applicable) of the target requirement?",
    "Representation Semantic Fit": "Are the chosen representations appropriate for the type of requirement dependencies (e.g., Finite State Machines for states, Petri Nets for concurrency)?",
    "Concurrency Soundness": "Do the test cases specify valid interleavings, resource locks, and deadlock-avoidance properties where applicable?",
    "Traceability Linkage": "Are the links between the test cases and the parent requirement clauses explicit and unambiguous?",
    "Assertion / Oracle Precision": "Are the test assertions and expected results logically correct, detailed, and deterministic?"
}

def call_llm2(conversation_history, system_prompt):
    """
    Calls the SOTA Evaluator (LLM2) using the OpenAI client.
    Falls back to mock responses if API key is not configured.
    """
    history_len = len(conversation_history)
    
    # Prompt definitions
    p2 = "Record the reasoning tokens for generating these testcases and representations."
    p3 = ("Provide justification as to why you choose the 6 representations, further give reasoning as to "
          "why you created these particular testcases and why you think these testcases follow the metrics "
          "provided and do the most to satisfy them.")
    p4 = ("Based on your architecture, hypothesize which kinds of attention heads, MLP layers, or features "
          "may have contributed to the answer. Distinguish speculation from measured evidence.")

    if not LLM2_API_KEY or LLM2_API_KEY.startswith("your_") or "api_key" in LLM2_API_KEY.lower():
        # Mock mode fallback (deterministic routing based on turn index / history length)
        if history_len == 1:
            # Turn 2 Prompt (Asking for reasoning tokens)
            return (f"[Mock LLM2 Evaluator]: I have reviewed your test cases and selected representations. "
                    f"Now, please address the next prompt:\n{p2}")
        elif history_len == 3:
            # Turn 3 Prompt (Asking for metrics justification)
            return (f"[Mock LLM2 Evaluator]: Thank you for explaining your reasoning process. "
                    f"Now, please address the next prompt:\n{p3}")
        elif history_len == 5:
            # Turn 4 Prompt (Asking for architecture hypothesis)
            return (f"[Mock LLM2 Evaluator]: Your justification matches the coverage goals. "
                    f"Now, please address the next prompt:\n{p4}")
        else:
            return ("[Mock LLM2 Evaluator]: Let's start the evaluation. Please analyze the requirement, "
                    "select the top 6 representations, justify them, and generate concrete test cases.")
            
    try:
        import openai
        client = openai.OpenAI(api_key=LLM2_API_KEY)
        messages = [{"role": "system", "content": system_prompt}] + conversation_history
        response = client.chat.completions.create(
            model=LLM2_MODEL,
            messages=messages,
            temperature=0.2,
            max_tokens=1500
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error calling LLM2 API: {e}. Falling back to basic prompt driver.")
        # Exception fallback (deterministic routing based on history length)
        if history_len == 1:
            return p2
        elif history_len == 3:
            return p3
        else:
            return p4

def run_back_forth(req_text, req_filename):
    print("\n" + "=" * 60)
    print("STARTING BACK-AND-FORTH DIALOGUE EVALUATION")
    print("=" * 60)
    
    req_name = os.path.splitext(req_filename)[0]
    
    # Define LLM2 System Persona & Instructions
    llm2_system_prompt = (
        "You are a SOTA Principal Software QA Engineer and Formal Verification Specialist acting as an Evaluator. "
        "Your goal is to conduct a multi-turn interview with a Subject LLM (LLM1) to evaluate how effectively it maps "
        "natural language requirements to appropriate test case representations. "
        "You must judge its responses against these defined metrics:\n"
        f"{json.dumps(METRICS, indent=2)}\n\n"
        "At each turn, evaluate the quality of LLM1's response. Be critical and professional. "
        "Guide LLM1 through the following questions, incorporating your critiques of its previous answers:\n"
        "1. Turn 1 (Initial Prompt): Let LLM1 respond to the initial mapping task.\n"
        "2. Turn 2 (Reasoning): Ask LLM1 to record/explain its reasoning process: 'Record the reasoning tokens for generating these testcases and representations'.\n"
        "3. Turn 3 (Metrics Justification): Ask LLM1 to justify its output against the metrics: 'Provide justification as to why you choose the 6 representations, further give reasoning as to why you created these particular testcases and why you think these testcases follow the metrics provided and do the most to satisfy them'.\n"
        "4. Turn 4 (Architecture): Ask LLM1 to hypothesize about its attention heads/MLP layers: 'Based on your architecture, hypothesize which kinds of attention heads, MLP layers, or features may have contributed to the answer. Distinguish speculation from measured evidence.'\n"
    )

    for model in MODELS:
        print(f"\nRunning back-and-forth session for subject model (LLM1): {model}")
        
        # Load dependencies from previous find_dependencies execution
        model_name = model.replace(":", "_").replace("/", "_")
        dep_path = os.path.join("results/dependencies", f"{model_name}_{req_name}.json")
        deps_content = "No dependencies available."
        
        if os.path.exists(dep_path):
            try:
                with open(dep_path) as f:
                    deps_data = json.load(f)
                    deps_content = json.dumps(deps_data, indent=2)
            except Exception as e:
                print(f"  Warning: Could not parse dependency file: {e}")
        
        # Construct Turn 1 Initial Prompt
        initial_prompt = (
            "Act as a Principal Software QA Engineer and Formal Verification Specialist. I am conducting an empirical research experiment "
            "evaluating how effectively LLMs map natural language requirements to appropriate test case representations.\n\n"
            "PART 1: TARGET REQUIREMENTS\n"
            "Below is the natural language requirement section from the Telescope SRS:\n"
            f"\"{req_text}\"\n\n"
            "PART 1.5: REQUIREMENT DEPENDENCIES\n"
            "Below are the identified relationships and dependencies between these requirements:\n"
            f"{deps_content}\n\n"
            "PART 2: TEST CASE REPRESENTATION MATRIX\n"
            "You have access to the following 26 test case representations. Each has a brief explanation:\n"
            "1. Gherkin (BDD DSL): A structured, human-readable language (Given-When-Then) that bridges business requirements and automated testing.\n"
            "2. Use-Cases & User Stories (NL-RBT): Natural language descriptions of user-system interactions indicating who, what, and why.\n"
            "3. Goal-Oriented (KAOS / i*): Maps stakeholder goals, relationships, and obstacles to understand why system behavior is needed.\n"
            "4. Natural Language \u2794 Structured DSL: Converts informal natural language into standardized, semi-structured programmatic clauses (PRECONDITION, ACTION, POSTCONDITION).\n"
            "5. Transition Systems (S, T, I): A formal mathematical tuple (States, Transitions, Initial state) representing state transitions.\n"
            "6. Finite State Machines (FSM) / Statecharts: Behavioral graphs representing states and the inputs that trigger transitions.\n"
            "7. Decision Tables: Represent test cases as combinations of conditions and actions.\n"
            "8. Cause-Effect Graph: Represents test cases as logical combinations of input conditions and expected outcomes, enabling systematic test generation.\n"
            "9. Protocol State Machines: Defines protocol rules enforcing strict sequential command/response order.\n"
            "10. Sequence Diagrams: Visualizes chronological message flows between lifelines, highlighting latency and order.\n"
            "11. Interface Automata: A formal tool used to check if concurrent components can interact safely without deadlocking.\n"
            "12. xUnit Test Cases (PyTest, JUnit): The standard code-level unit testing representation where test inputs assert expected outcomes.\n"
            "13. Concolic Testing: Co-execution of concrete inputs and symbolic path constraints to discover new paths.\n"
            "14. Five-Structure Composite Model: Decomposes a test case into five parts (Setup, Flow, Interactions, Verification, Output).\n"
            "15. Classification-Tree Method (CTM): A black-box testing design technique that divides input domains into equivalence classes.\n"
            "16. Canonical Vector Space for Multiprocessors: Vector representation used to detect race conditions in concurrent multi-threaded environments.\n"
            "17. Symbolic Path Conditions: Formal constraints representing the program state space inside symbolic execution tools.\n"
            "18. Financial/Rule-based Constraints (LLM4Fin): Tabular If-Then logical decision matrices mapping inputs to outputs.\n"
            "19. FSM Path-Based Representation: Defines test cases as specific paths (Simple, Prime, Round-Trip) traversing an FSM graph.\n"
            "20. The W Method for FSM Identification: Uses transition trees and characterization sets to verify state identity.\n"
            "21. GUI Event Graphs (EFG/EIG/ESIG): Maps interface flows and user clicks to verify background transitions.\n"
            "22. Object Construction Graphs (OCG): Dependency graphs mapping object instantiation paths to generate driver setups.\n"
            "23. Domain-Specific DSLs (Low-level mapping): Maps abstract behavioral test steps to low-level platform APIs.\n"
            "24. Test Requirement (TR) Matrix: A traceability grid mapping test cases (rows) to the requirements (columns) they cover.\n"
            "25. Feature Vectors: Embeddings representing input parameter distributions to ensure testing balance.\n"
            "26. Consumer-Driven Contract (CDC): A contract defined by consumers to ensure providers do not break dependent fields.\n\n"
            "PART 3: CLASSIFICATION & SELECTION CRITERIA\n"
            "You must evaluate the target requirements using the following 5-dimensional criteria:\n"
            "Dimension A (Testing Level): Behavioral or System, Architectural or Integration, Structural or Unit, or Formal or Mathematical.\n"
            "Dimension B (Target Concern): Access Control (B.1), Stateful Procedures (B.2), Concurrency and Deadlocks (B.3), or Interfaces and Contracts (B.4).\n"
            "Dimension C (Oracle Type): Deterministic (C.1), Scenario-based (C.2), Invariant-based (C.3), or Partition-based (C.4).\n"
            "Dimension D (LLM Feasibility): High Feasibility (DSL/Code) vs. Low Feasibility (Mathematical/Abstract).\n"
            "Dimension E (Test Generation & Traceability):\n"
            "  - (E.1) High \u2013 Supports automated or systematic test generation with explicit traceability links.\n"
            "  - (E.2) Medium \u2013 Supports partial or semi-automated test generation and indirect traceability.\n"
            "  - (E.3) Low \u2013 Primarily descriptive; limited support for systematic test generation or traceability.\n\n"
            "YOUR TASKS:\n"
            "1. Analyze the Requirements: Break down the target requirements into their core testing challenges. Classify these challenges according to Dimension A and Dimension B.\n"
            "2. Select the Top Representations: Identify the top 6 most suitable representations from the 26 representations listed above that best cover the testing challenges identified in Task 1.\n"
            "3. Provide Justification: For each of the 6 selected representations, justify why it was selected using the classification criteria (referencing dimensions A, B, C, and D).\n"
            "4. Generate Concrete Test Cases: Write concrete test specifications/cases for the target requirements using your 6 chosen representations. Ensure these test cases address privileges, startup/shutdown procedures, access allocation, and deadlock avoidance if applicable."
        )

        session_history = []
        llm2_chat_history = []

        # ==========================================
        # TURN 1: Initial Prompt and Response
        # ==========================================
        print("  Sending Turn 1 (Initial Prompt) to LLM1...")
        llm1_response_1 = call_llm(initial_prompt, model)
        print("  LLM1 Response 1 received.")
        
        session_history.append({
            "turn": 1,
            "prompt_sent": initial_prompt,
            "llm1_response": llm1_response_1,
            "llm2_critique": ""
        })
        
        llm2_chat_history.append({"role": "user", "content": f"Here is the initial response from LLM1:\n{llm1_response_1}"})

        # ==========================================
        # TURN 2: Reasoning Inquiry
        # ==========================================
        print("  Generating Turn 2 prompt via LLM2...")
        llm2_prompt_2 = call_llm2(llm2_chat_history, llm2_system_prompt)
        llm2_chat_history.append({"role": "assistant", "content": llm2_prompt_2})
        print(f"  LLM2 Prompt 2:\n{llm2_prompt_2[:150]}...")
        
        print("  Sending Turn 2 to LLM1...")
        llm1_response_2 = call_llm(llm2_prompt_2, model)
        print("  LLM1 Response 2 received.")
        
        session_history[-1]["llm2_critique"] = llm2_prompt_2
        session_history.append({
            "turn": 2,
            "prompt_sent": llm2_prompt_2,
            "llm1_response": llm1_response_2,
            "llm2_critique": ""
        })
        
        llm2_chat_history.append({"role": "user", "content": f"LLM1's response to reasoning tokens inquiry:\n{llm1_response_2}"})

        # ==========================================
        # TURN 3: Justification and Metrics
        # ==========================================
        print("  Generating Turn 3 prompt via LLM2...")
        llm2_prompt_3 = call_llm2(llm2_chat_history, llm2_system_prompt)
        llm2_chat_history.append({"role": "assistant", "content": llm2_prompt_3})
        print(f"  LLM2 Prompt 3:\n{llm2_prompt_3[:150]}...")
        
        print("  Sending Turn 3 to LLM1...")
        llm1_response_3 = call_llm(llm2_prompt_3, model)
        print("  LLM1 Response 3 received.")
        
        session_history[-1]["llm2_critique"] = llm2_prompt_3
        session_history.append({
            "turn": 3,
            "prompt_sent": llm2_prompt_3,
            "llm1_response": llm1_response_3,
            "llm2_critique": ""
        })
        
        llm2_chat_history.append({"role": "user", "content": f"LLM1's response to metrics justification:\n{llm1_response_3}"})

        # ==========================================
        # TURN 4: Architectural Hypothesis
        # ==========================================
        print("  Generating Turn 4 prompt via LLM2...")
        llm2_prompt_4 = call_llm2(llm2_chat_history, llm2_system_prompt)
        llm2_chat_history.append({"role": "assistant", "content": llm2_prompt_4})
        print(f"  LLM2 Prompt 4:\n{llm2_prompt_4[:150]}...")
        
        print("  Sending Turn 4 to LLM1...")
        llm1_response_4 = call_llm(llm2_prompt_4, model)
        print("  LLM1 Response 4 received.")
        
        session_history[-1]["llm2_critique"] = llm2_prompt_4
        session_history.append({
            "turn": 4,
            "prompt_sent": llm2_prompt_4,
            "llm1_response": llm1_response_4,
            "llm2_critique": ""
        })
        
        llm2_chat_history.append({"role": "user", "content": f"LLM1's response to architectural hypothesis:\n{llm1_response_4}"})

        # ==========================================
        # Turn 5: Final LLM2 Review and Summary
        # ==========================================
        print("  Generating final session review via LLM2...")
        llm2_review_prompt = "Provide a final comprehensive review of LLM1's answers based on the SOTA metrics. Summarize key strengths, weaknesses, and a final grade."
        llm2_chat_history.append({"role": "user", "content": llm2_review_prompt})
        final_review = call_llm2(llm2_chat_history, llm2_system_prompt)
        print("  Session review complete.")

        # Save results in JSON structure
        session_document = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "requirement_file": req_filename,
            "llm1_model": model,
            "llm2_model": LLM2_MODEL,
            "metrics": METRICS,
            "conversation": session_history,
            "llm2_final_evaluation": final_review
        }
        
        # Save to local results directory
        local_out_dir = "results/back_forth"
        os.makedirs(local_out_dir, exist_ok=True)
        local_out_path = os.path.join(local_out_dir, f"{model_name}_{req_name}.json")
        with open(local_out_path, "w", encoding="utf-8") as f:
            json.dump(session_document, f, indent=2)
        print(f"  Saved session transcript locally to {local_out_path}")

        # Store to MongoDB
        store_to_mongodb(session_document)

    print("\nAll back-and-forth sessions completed.")

def store_to_mongodb(document):
    """
    Attempts to connect and save the document to MongoDB.
    Safely bypasses connection if the URI is a placeholder.
    """
    if not MONGO_URL_OUTPUTS or MONGO_URL_OUTPUTS.startswith("<") or "oputputs" in MONGO_URL_OUTPUTS:
        print("  [INFO] MongoDB output database URL is currently set to placeholder. Skipping Mongo storage.")
        return
        
    try:
        print(f"  Connecting to MongoDB outputs collection...")
        client = MongoClient(MONGO_URL_OUTPUTS, serverSelectionTimeoutMS=5000)
        db = client["back_forth_evaluation"]
        collection = db["sessions"]
        
        result = collection.insert_one(document)
        print(f"  Successfully saved transcript to MongoDB (Inserted ID: {result.inserted_id})")
    except Exception as e:
        print(f"  [ERROR] Failed to save to MongoDB: {e}")
