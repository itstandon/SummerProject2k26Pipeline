import os
import requests

MODELS = [
    "qwen2.5:3b",
    #"llama3.2:3b",
    "gemma3:4b"
]

# The "SOTA" evaluator model used for Gate 3 (FSA) judging, plus its API key.
# Configure via a .env file or exported shell variables:
#   LLM2_MODEL=gpt-4o
#   LLM2_API_KEY=sk-...
LLM2_MODEL = os.environ.get("LLM2_MODEL", "gpt-4o")
LLM2_API_KEY = os.environ.get("LLM2_API_KEY")

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"


def call_llm(prompt, model, timeout=1800):
    """
    Routes to the right backend based on `model`:
      - If `model` matches LLM2_MODEL (e.g. "gpt-4o"), call the OpenAI API.
      - Otherwise, treat it as a local Ollama model name and call the
        local Ollama server.
    Falls back to a mock response if the relevant backend call fails,
    so the pipeline can still be exercised end-to-end without live
    services during development/testing.
    """
    if model in MODELS:
        return _call_ollama(prompt, model, timeout)
    return _call_openai(prompt, model, timeout)


def _call_openai(prompt, model, timeout=1800):
    if not LLM2_API_KEY or LLM2_API_KEY == "your_sota_api_key_here":
        print(f"  [OpenAI call skipped: LLM2_API_KEY is not set]. Using high-quality mock response for {model}.")
        return get_mock_response(prompt, model)

    try:
        response = requests.post(
            OPENAI_CHAT_URL,
            headers={
                "Authorization": f"Bearer {LLM2_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"  [OpenAI call failed: {e}]. Using high-quality mock response for {model}.")
        return get_mock_response(prompt, model)


def _call_ollama(prompt, model, timeout=1800):
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_ctx": 8192,
                    "num_predict": 2048,
                }
            },
            timeout=timeout
        )
        response.raise_for_status()
        return response.json()["response"]
    except Exception as e:
        print(f"  [Ollama call failed: {e}]. Using high-quality mock response for {model}.")
        return get_mock_response(prompt, model)


def get_mock_response(prompt, model):
    prompt_lower = prompt.lower()
    
    # TURN 1: Initial Prompt (Select Representations Catalog)
    if "available representations (30 options)" in prompt_lower or "select the top 6" in prompt_lower or "select_representations" in prompt_lower:
        return f"""<think>
Reasoning Process:
1. Analyze Requirement {model}:
   - The requirement covers operations privileges (access control), startup/shutdown stateful transitions, and deadlock-free resource allocation (concurrency).
2. Map to classification dimensions:
   - Access control is Behavioral/System level.
   - Startup/shutdown procedures are Architectural/Integration level.
   - Deadlock-free resource allocation is Formal/Mathematical level.
3. Select appropriate representations from the 30 library options:
   - Gherkin (BDD DSL) for scenario-level startup/shutdown.
   - FSM / Statecharts for stateful transition paths.
   - Decision Tables for privilege rules mapping.
   - Sequence Diagrams for component startup/shutdown communication flows.
   - Petri Nets for formal deadlock-freedom verification.
   - xUnit Test Cases for unit-level execution constraints.
4. Draft concrete test cases for all selections to ensure maximum coverage of the original requirement clauses.
</think>
### Subject Model ({model}) Response - Turn 1 (Initial Test Case Mapping)

#### 1. Analysis of Requirements (Dimension A & B Classification)
*   **REQ_0037 (Operation Privileges)**:
    *   *Classification*: Dimension A (System / Behavioral), Dimension B.1 (Access Control).
    *   *Testing Challenge*: Verifying user privileges (Admin, Operator, Guest) assigned dynamically during login.
*   **REQ_0038 (Access Mode Allocation & Deadlock-freedom)**:
    *   *Classification*: Dimension A (Formal / Mathematical), Dimension B.3 (Concurrency & Deadlocks).
    *   *Testing Challenge*: Asserting that concurrent resource allocation avoids circular wait states and prevents deadlocks.
*   **REQ_0040 & REQ_0042 (Telescope and Instrument Startup/Shutdown)**:
    *   *Classification*: Dimension A (Architectural / Integration), Dimension B.2 (Stateful Procedures).
    *   *Testing Challenge*: Validating sequential startup/shutdown states and ensuring instrument activities do not interfere with telescope operations.

#### 2. Selected Top 6 Representations
1.  **Gherkin (BDD DSL)** (Scenario/Behavioral): Perfect for documenting high-level startup/shutdown sequences.
2.  **Finite State Machines (FSM)** (Stateful/Transitions): Models the transition flows (OFF -> STARTING -> READY -> FAULT) of the telescope.
3.  **Decision Tables** (Logical/Rules): Captures access mode allocations and privileges based on login input combinations.
4.  **Sequence Diagrams** (Concurrency/Interaction): Visualizes the timelines of concurrent startup sequences to verify non-interference.
5.  **Petri Nets** (Stateful/Transitions): Mathematically models concurrent resource locks to guarantee deadlock-freedom.
6.  **xUnit Test Cases** (Programmatic/Code): Executable unit test scripts to verify privilege constraints and variable bindings.

#### 3. Classification Justification
*   **Gherkin**: Dimension A (Behavioral), Dimension B.2 (Stateful), Dimension C.2 (Scenario-based oracle). Matches stakeholder readability goals.
*   **FSM**: Dimension A (Architectural), Dimension B.2 (Stateful), Dimension C.3 (Invariant-based oracle).
*   **Decision Tables**: Dimension A (Unit), Dimension B.1 (Access Control), Dimension C.4 (Partition-based oracle).
*   **Sequence Diagrams**: Dimension A (Integration), Dimension B.4 (Interfaces), Dimension C.1 (Deterministic oracle).
*   **Petri Nets**: Dimension A (Mathematical), Dimension B.3 (Concurrency), Dimension C.3 (Invariant-based).
*   **xUnit**: Dimension A (Unit), Dimension B.4 (Interfaces), Dimension C.1 (Deterministic).

#### 4. Concrete Test Cases

##### Representation 1: Gherkin (Startup Scenario)
```gherkin
Feature: Telescope Startup Sequence
  Scenario: Successful Telescope Startup
    Given the telescope is in state OFF
    When the startup procedure is initiated
    Then the system transitions to state STARTING
    And drive motors perform self-testing
    And the system transitions to state READY
```

##### Representation 2: Finite State Machine (Transitions)
*   **States**: `OFF`, `STARTING`, `READY`, `FAULT`
*   **Transitions**:
    *   `OFF` + `startup_event` -> `STARTING` (Action: power_on())
    *   `STARTING` + `self_test_pass` -> `READY`
    *   `STARTING` + `self_test_fail` -> `FAULT`

##### Representation 3: Decision Table (Privileges)
| Condition: User Role | Action: Write Configuration | Action: Trigger Shutdown | Action: Read Status |
| :--- | :---: | :---: | :---: |
| Admin | ALLOW | ALLOW | ALLOW |
| Operator | ALLOW | DENY | ALLOW |
| Guest | DENY | DENY | ALLOW |

##### Representation 4: Sequence Diagram (Non-Interference)
```mermaid
sequenceDiagram
    participant Telescope
    participant InstrumentA
    Telescope->>Telescope: collectTelemetry()
    Note over InstrumentA: Startup initiated
    InstrumentA->>InstrumentA: startup()
    activate InstrumentA
    Note over Telescope: Telemetry must continue uninterrupted
    deactivate InstrumentA
```

##### Representation 5: Petri Net (Deadlock-Free Allocation)
*   **Places**: $P_1$ (Resource Available), $P_2$ (Request Pending), $P_3$ (Resource Locked)
*   **Transitions**: $T_1$ (Request Lock), $T_2$ (Release Lock)
*   **Token flow**: Token in $P_1$ goes to $P_3$ when $T_1$ fires, ensuring mutual exclusion.

##### Representation 6: xUnit Test Case (PyTest)
```python
def test_privilege_login_access():
    session = LoginSystem.login(user="Guest", credentials="123")
    assert session.privileges == "Guest"
    assert session.can_write_config() is False
    assert session.can_shutdown() is False
    assert session.can_read_status() is True
```"""

    # TURN 2: Metrics Justification
    elif "justify ur choices against the following framework metrics" in prompt_lower or "representational suitability score" in prompt_lower:
        return f"""<think>
Reasoning Process:
1. Examine chosen representations (Gherkin, FSM, Decision Tables, Sequence Diagrams, Petri Nets, xUnit).
2. Align each representation with the new metrics.md framework gates:
   - RSS (Concern Alignment, Abstraction, Occam's Razor, LLM Feasibility).
   - SFV (adherence to syntax rules and schema standards).
   - FSA (Clause Coverage, Negative/Error Coverage, Oracle Assertiveness, Boundary Coverage).
3. Construct detailed justifications for each gate.
</think>
### Subject Model ({model}) Response - Turn 2 (Metrics Justification)

Here is how the generated test cases and selected representations satisfy the 3-Gate metrics.md framework:

1.  **Representational Suitability Score (RSS)**:
    - *Concern Alignment*: Mapped state transitions (startup/shutdown) to FSM, concurrent resource locking to Petri Nets, and user privileges/modes to Decision Tables.
    - *Abstraction Fit*: Matched integration-level telemetry to Sequence Diagrams, and code-level bindings to xUnit.
    - *Occam's Razor*: Selected minimal Gherkin scenarios for happy paths instead of full state charts.
    - *LLM Feasibility*: Selected standard formats (xUnit, JSON) that avoid generation hallucinations.
2.  **Syntactic Form Validity (SFV)**:
    - Evaluated elements comply with strict grammar checks. For example, Gherkin scenarios use standard Given-When-Then syntax without nested blocks, and the Petri Net defines a valid mathematical graph tuple (P, T, F, M0).
3.  **Functional Semantic Adequacy (FSA)**:
    - *Clause Coverage*: Verified all clauses of 2.10 including dynamic login privileges and deadlock avoidance.
    - *Negative/Error Coverage*: FSM transitions model startup Motor Fault conditions, and Sequence Diagrams check command timeout paths.
    - *Oracle Assertiveness*: Precise boolean assert conditions are used in the PyTest xUnit test cases.
    - *Boundary Coverage*: Tested input privilege combinations on decision tables."""

    # FALLBACK / DEFAULT
    else:
        return f"""<think>
Reasoning Process:
1. Fallback matched. Returning standard response.
</think>
### Subject Model ({model}) Response - Fallback
I am ready to proceed. Please provide the requirement and evaluation metrics."""