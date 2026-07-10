import os
import json
import re
import datetime
from dotenv import load_dotenv
from pymongo import MongoClient

# Import LLM1 caller and models list
from .call_llm import call_llm, MODELS

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

    if not LLM2_API_KEY or LLM2_API_KEY.startswith("your_") or "api_key" in LLM2_API_KEY.lower():
        # Mock mode fallback (deterministic routing based on turn index / history length)
        # Check if the last query asks for final comprehensive review
        if conversation_history and "comprehensive review" in conversation_history[-1]["content"].lower():
            return """[Mock LLM2 Evaluator]: Comprehensive Review Report and Final Grading

### SOTA Dialog Evaluation Scores:
1. Requirements Coverage: 4.8 / 5.0 (Excellent)
   - Rationale: The subject model successfully verified privileges (via Decision Tables/xUnit), startup/shutdown state sequences (via Gherkin/FSM), access allocation constraints (via Decision Tables), and deadlock-freedom properties (via Petri Nets).
2. Representation Semantic Fit: 5.0 / 5.0 (Optimal)
   - Rationale: Selected representations correspond perfectly to requirement dependencies (FSM for states, Petri Nets for concurrency, Decision Tables for privilege rules).
3. Concurrency Soundness: 4.6 / 5.0 (Excellent)
   - Rationale: Models interleavings, locks, and proves deadlock-freedom mathematically using Petri Net places/transitions.
4. Traceability Linkage: 4.8 / 5.0 (Excellent)
   - Rationale: Assertions and scenarios contain explicit reference tags mapping directly to REQ_0037 and REQ_0038.
5. Assertion / Oracle Precision: 4.7 / 5.0 (Excellent)
   - Rationale: Oracles are deterministic, and code test blocks verify exact status variables.

### Final Grade: A (Excellent)"""
        elif history_len == 1:
            # Turn 2 Prompt (Asking for reasoning tokens)
            return (f"[Mock LLM2 Evaluator]: I have reviewed your test cases and selected representations. "
                    f"Now, please address the next prompt:\n{p2}")
        elif history_len == 3:
            # Turn 3 Prompt (Asking for metrics justification)
            return (f"[Mock LLM2 Evaluator]: Thank you for explaining your reasoning process. "
                    f"Now, please address the next prompt:\n{p3}")
        else:
            return ("[Mock LLM2 Evaluator]: Let's start the evaluation. Please analyze the requirement, "
                    "select the top representations, justify them, and generate concrete test cases.")
            
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
        else:
            return p3

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
            "Requirement -> Test Case Representation Selection & Generation Prompt\n"
            "SYSTEM / INSTRUCTION\n"
            "Act as a Principal Software QA Engineer and Formal Verification Specialist. You are one stage in an automated pipeline that maps natural-language requirements to appropriate test case representations, then generates concrete test cases in those representations.\n"
            "INPUT\n"
            f"Requirement: \"{req_text}\"\n"
            f"Requirement ID: {req_name}\n"
            f"Requirement Dependencies: {deps_content}\n\n"
            "REPRESENTATION LIBRARY (30 options)\n"
            "Gherkin (BDD DSL) - Given-When-Then, bridges business requirements and automated testing.\n"
            "Use-Cases & User Stories (NL-RBT) - who/what/why interaction narratives.\n"
            "Goal-Oriented (KAOS / i*) - stakeholder goals, relationships, obstacles.\n"
            "Natural Language -> Structured DSL - PRECONDITION/ACTION/POSTCONDITION clauses.\n"
            "Transition Systems (S, T, I) - formal tuple of states, transitions, initial state.\n"
            "Finite State Machines (FSM) / Statecharts - states and triggering inputs.\n"
            "Decision Tables - conditions x actions combinations.\n"
            "Cause-Effect Graph - logical input-condition combinations to expected outcomes.\n"
            "Protocol State Machines - strict sequential command/response rules.\n"
            "Sequence Diagrams - chronological message flows between lifelines.\n"
            "Interface Automata - formal check for safe, deadlock-free concurrent interaction.\n"
            "xUnit Test Cases (PyTest, JUnit) - code-level input/assert unit tests.\n"
            "Concolic Testing - concrete + symbolic path co-execution.\n"
            "Five-Structure Composite Model - Setup, Flow, Interactions, Verification, Output.\n"
            "Classification-Tree Method (CTM) - input domain partitioned into equivalence classes.\n"
            "Canonical Vector Space for Multiprocessors - vectors for race-condition detection.\n"
            "Symbolic Path Conditions - formal state-space constraints in symbolic execution.\n"
            "Financial/Rule-based Constraints (LLM4Fin) - tabular If-Then decision matrices.\n"
            "FSM Path-Based Representation - Simple/Prime/Round-Trip paths through an FSM.\n"
            "The W Method for FSM Identification - transition trees + characterization sets.\n"
            "GUI Event Graphs (EFG/EIG/ESIG) - interface flows and click-driven transitions.\n"
            "Object Construction Graphs (OCG) - object instantiation dependency graphs.\n"
            "Domain-Specific DSLs (low-level mapping) - abstract steps mapped to platform APIs.\n"
            "Test Requirement (TR) Matrix - traceability grid of test cases x requirements.\n"
            "Feature Vectors - embeddings of input parameter distributions for test balance.\n"
            "Consumer-Driven Contract (CDC) - consumer-defined contract guarding provider fields.\n"
            "UML Testing Profile (UTP) - UML classes/sequences stereotyped as <<TestContext>>, <<TestCase>>, <<SUT>>, <<Verdict>> for model-driven testing.\n"
            "Petri Nets - bipartite graph of places/transitions/token markings (P, T, F, M0), used to verify concurrent system behavior.\n"
            "Message Sequence Charts (MSC) - ITU-T Z.120 standard notation for instance lifelines and timed message exchanges between components.\n"
            "Temporal Logic (LTL) - boolean propositions extended with temporal operators (Always, Eventually, Next, Until) to specify time-ordered execution properties.\n\n"
            "CLASSIFICATION DIMENSIONS\n"
            "Dimension A (Testing Level): Behavioral/System, Architectural/Integration, Structural/Unit, or Formal/Mathematical.\n\n"
            "Dimension B (Target Concern): An open, controlled taxonomy - not a fixed 4-item list. Requirements vary too widely in domain for any small fixed set to cover them all (e.g. a timing/protocol requirement is poorly served by forcing it into \"Interfaces & Contracts\").\n"
            "Seed taxonomy (check these first, for consistency across pipeline runs):\n"
            "B.1 Access Control (privileges, authentication, authorization)\n"
            "B.2 Stateful Procedures (workflows, startup/shutdown, multi-step operational sequences)\n"
            "B.3 Concurrency & Deadlocks (resource contention, race conditions, mutual exclusion)\n"
            "B.4 Interfaces & Contracts (API/message boundaries, protocol compliance between components)\n"
            "B.5 Timing & Performance (latency, timeouts, throughput, real-time deadlines)\n"
            "B.6 Data Integrity & Validation (input/output correctness, state consistency, boundary values)\n"
            "B.7 Fault Tolerance & Error Handling (recovery, degraded modes, exception paths)\n"
            "B.8 Security (confidentiality, integrity threats, attack surfaces - distinct from B.1's access control)\n"
            "B.9 Resource Management (allocation, limits, cleanup, leak prevention)\n"
            "Rule for new tags: only introduce a new concern label (as B.custom-<short-name>) if a challenge genuinely does not fit any seed category above - do not force-fit, but do not mint a new tag casually either. List any newly-minted tags in a separate \"proposed_new_concerns\" field in the JSON output (see schema below) so they can be reviewed and folded into the seed taxonomy for future runs, rather than silently fragmenting the taxonomy across pipeline runs.\n\n"
            "Dimension C (Oracle Type): Deterministic (C.1), Scenario-based (C.2), Invariant-based (C.3), Partition-based (C.4).\n\n"
            "Dimension D (LLM Feasibility): High (DSL/Code) vs. Low (Mathematical/Abstract).\n\n"
            "Dimension E (Test Generation & Traceability): High (E.1) - automated/systematic generation with explicit traceability; Medium (E.2) - partial/semi-automated, indirect traceability; Low (E.3) - descriptive only.\n\n"
            "TASKS\n"
            "Task 1 - Decompose the requirement. Break the requirement into its discrete testing challenges (one per distinct behavior/constraint it imposes - do not merge unrelated concerns, do not split a single atomic clause artificially). For each challenge, tag it with its Dimension A level and Dimension B concern(s).\n"
            "Task 2 - Select representations. Choose 4-6 representations from the library (state your chosen count and why) that, as a set, collectively cover every (A, B) tag identified in Task 1 with minimal redundancy. Prefer coverage breadth over picking multiple representations that serve the same challenge, unless a challenge genuinely needs both a scenario-level and a formal-level treatment (e.g., a concurrency/deadlock challenge often needs both a human-readable procedure and a formal model).\n"
            "Task 3 - Justify each selection. For each chosen representation, state which challenge(s) from Task 1 it addresses, and classify it on Dimensions A, B, C, D, and E. Keep justifications to 2-3 sentences each - reasoning, not padding.\n"
            "Task 4 - Generate concrete test cases. For each of the selected representations, write actual test case(s) instantiated against the requirement - not generic templates. Every distinct challenge from Task 1 must be covered by at least one concrete test case somewhere across the 4-6 representations. Include edge cases and negative cases where the requirement implies them (e.g., failure/contention/rollback paths), not just the happy path.\n\n"
            "OUTPUT FORMAT\n"
            "Return both a human-readable report and a machine-parseable JSON block, in this order:\n"
            "1. A concise markdown report (Tasks 1-4, in order).\n"
            "2. A fenced ```json block at the end with this exact schema:\n"
            "{\n"
            "  \"requirement_id\": \"{REQ_ID}\",\n"
            "  \"proposed_new_concerns\": [\n"
            "    {\n"
            "      \"tag\": \"B.custom-<short-name>\",\n"
            "      \"reason\": \"string explaining why no seed B.1-B.9 category fit\"\n"
            "    }\n"
            "  ],\n"
            "  \"challenges\": [\n"
            "    {\n"
            "      \"id\": \"C1\",\n"
            "      \"description\": \"string\",\n"
            "      \"dimension_a\": \"Behavioral/System | Architectural/Integration | Structural/Unit | Formal/Mathematical\",\n"
            "      \"dimension_b\": [\"B.1 | B.2 | ... | B.9 | B.custom-<short-name>\"]\n"
            "    }\n"
            "  ],\n"
            "  \"selected_representations\": [\n"
            "    {\n"
            "      \"name\": \"string (must match library name exactly)\",\n"
            "      \"covers_challenges\": [\"C1\"],\n"
            "      \"dimension_a\": \"string\",\n"
            "      \"dimension_b\": [\"string\"],\n"
            "      \"dimension_c\": \"C.1 | C.2 | C.3 | C.4\",\n"
            "      \"dimension_d\": \"High | Low\",\n"
            "      \"dimension_e\": \"E.1 | E.2 | E.3\",\n"
            "      \"justification\": \"string\"\n"
            "    }\n"
            "  ],\n"
            "  \"test_cases\": [\n"
            "    {\n"
            "      \"representation\": \"string\",\n"
            "      \"challenge_ids\": [\"C1\"],\n"
            "      \"case_id\": \"string\",\n"
            "      \"content\": \"string (the actual test case, in that representation's native notation)\"\n"
            "    }\n"
            "  ]\n"
            "}\n"
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
        # Turn 4: Final LLM2 Review and Summary
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
