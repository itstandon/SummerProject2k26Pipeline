# SummerProject2k26Pipeline

# Requirements-to-Test-Case Generation Pipeline

## What This Is

An automated pipeline that takes a Software Requirements Specification (SRS) section,
resolves its dependencies from a MongoDB database, and generates a complete test case
suite using multiple LLMs. The generated suites are then evaluated for structural
validity and compared against expert-written ground truth.

---

## What Has Been Done So Far

### Pipeline Stages (Current Architecture)

```
SRS Text File
     │
     ▼
[1] find_dependencies.py
     │  Parses REQ_IDs from the selected section,
     │  fetches their dependency links from MongoDB,
     │  and pulls in the content of any out-of-section
     │  requirements they depend on.
     │  Output: results/dependencies/{model}_{req_name}.json
     │
     ▼
[2] generate_testcases.py
     │  Runs two prompt "phases" per model, straight from
     │  reqs + dependencies — no representation-selection
     │  step in between (that stage was removed).
     │
     │  phase1_basic         → prompts/generate_testcases_basic.txt
     │  phase2_metrics_aware → prompts/generate_testcases_metrics_aware.txt
     │
     │  Output: results/test_cases/{phase}/{model}_{req_name}/{req_name}.txt
     │          results/test_cases/{phase}/{model}_{req_name}/{req_name}_meta.json
     │
     ▼
[3] run_metrics.py  (Gate 2: SFV — Syntactic Form Validity)
     │  Heuristic, LLM-free check that every generated suite
     │  follows the required test-case template structure
     │  (Test Case ID / Title / Preconditions / Steps /
     │  Expected Result). Scores both phases for every model.
     │
     │  Output: results/metrics/{phase}/{model}_{req_name}/{req_name}_sfv.json
     │          results/metrics/{req_name}_sfv_summary.json
     │
     ▼
[4] compare_with_expert  (run from post-generation menu)
     │  Compares both phases against human expert ground truth
     │  where it exists for the selected requirement file.
     │
     ▼
[Optional post-generation menu]
     ├── Back and forth      — iterative refinement loop
     ├── Compare with expert — expert ground-truth alignment
     ├── Coverage analysis   — cross-model coverage stats
     └── Evaluate metrics    — re-run Gate 2 SFV on demand
```

### Prompt Files (in `prompts/`)

| File | Used By | Phase |
|---|---|---|
| `generate_testcases_basic.txt` | `generate_testcases.py` | phase1_basic |
| `generate_testcases_metrics_aware.txt` | `generate_testcases.py` | phase2_metrics_aware |
| `fsa_evaluate.txt` | `fsa.py` | FSA/Gate 3 evaluation |
| `select_representations.txt` | `select_representations.py` | **Legacy — not called by the main pipeline** |
| `Representations.md` | `select_representations.py` | **Legacy — not called by the main pipeline** |

### What Is Legacy (Still Present but Not Called)

- **`select_representations.py`** — used to select the best test representation
  (Gherkin, FSM, Decision Table, etc.) before generating test cases. This whole
  stage has been removed from the active pipeline. `generate_testcases.py` now
  goes straight from dependencies to generation.
- **`gate1_rss.py`** — Representation Suitability Score, used to validate
  representation choices. Removed from the active pipeline along with representation
  selection.
- **Gate 3 (FSA / `fsa.py`)** — Functional Semantic Adequacy scoring via an
  evaluator LLM. The module exists and is fully implemented but is not wired into
  the CLI's automated run sequence. It can be called manually.

### Models Used

Configured in `call_llm.py`. Current list:

| Model | Backend |
|---|---|
| `qwen2.5:3b` | Local Ollama |
| `gemma3:4b` | Local Ollama |
| `openai/gpt-oss-120b` | Groq API |

The SOTA evaluator (`LLM2_MODEL`) is also a Groq-hosted model, configured via
environment variables.

### Scoring / Gates

| Gate | Module | What It Checks | Automated? |
|---|---|---|---|
| Gate 1 — RSS | `gate1_rss.py` | Representation suitability | Legacy / manual only |
| Gate 2 — SFV | `gate2_sfv.py` | Template structure validity | ✅ Yes — runs after generation |
| Gate 3 — FSA | `fsa.py` | Semantic coverage + groundedness | Manual / optional |

---

## Project Structure

```
project/
├── cli.py                        # Main entry point
├── call_llm.py                   # LLM routing (Ollama / Groq)
├── find_dependencies.py          # MongoDB dependency resolution
├── generate_testcases.py         # Test suite generation (both phases)
├── run_metrics.py                # Gate 2 SFV scoring
├── gate2_sfv.py                  # SFV heuristic implementation
├── gate1_rss.py                  # (Legacy) Representation suitability scoring
├── fsa.py                        # (Optional) Gate 3 FSA evaluator
├── groundedness.py               # Mg (groundedness) sub-metric
├── config.py                     # All thresholds, weights, group mappings
├── select_representations.py     # (Legacy) Representation selection
├── dependencies_testcases.py     # (Stub)
│
├── prompts/
│   ├── generate_testcases_basic.txt
│   ├── generate_testcases_metrics_aware.txt
│   ├── fsa_evaluate.txt
│   ├── select_representations.txt    # legacy
│   └── Representations.md            # legacy
│
└── results/                      # Auto-created on first run
    ├── dependencies/
    ├── test_cases/
    │   ├── phase1_basic/
    │   └── phase2_metrics_aware/
    └── metrics/
```

---

## Prerequisites

### 1. Python Environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install pymongo python-dotenv requests
```

### 2. Environment Variables

Create a `.env` file in the project root:

```env
# MongoDB connection (where your SRS requirements are stored)
MONGO_URI=mongodb://localhost:27017
DB_NAME=your_database_name
COLLECTION_NAME=your_collection_name

# Groq API — required for cloud model calls and the evaluator LLM
LLM2_MODEL=openai/gpt-oss-120b
LLM2_API_KEY=gsk_your_groq_api_key_here

# Optional retry tuning
GROQ_MAX_RETRIES=5
GROQ_BACKOFF_BASE_SECONDS=5
```

### 3. Local Ollama (for local models)

If you want to run `qwen2.5:3b` or `gemma3:4b` locally:

```bash
# Install Ollama: https://ollama.com
ollama pull qwen2.5:3b
ollama pull gemma3:4b
ollama serve   # keep this running in a separate terminal
```

If Ollama is not running, those models will fall back to a mock response
automatically — the pipeline won't crash.

### 4. MongoDB

Your MongoDB collection must have documents with at least these fields:

```json
{
  "req_id": "REQ_0037",
  "title": "...",
  "content": "...",
  "dependencies": [
    { "relation": "depends_on", "target": "REQ_0012" }
  ]
}
```

---

## How to Run

### Standard Run (from the project root)

```bash
cd path/to/project
source venv/bin/activate
python3 -m scripts.cli
```

> Run as a module (`-m scripts.cli`), not directly (`python scripts/cli.py`),
> so that relative imports inside the package resolve correctly.

### Step-by-Step Walk-Through

**1. Choose a grouping level** — controls how requirements are grouped
into exportable sections:

```
0 -> X          (top-level, e.g. "3")
1 -> X.X        (e.g. "3.2")
2 -> X.X.X      (e.g. "3.2.1")
3 -> X.X.X.X    (e.g. "3.2.1.4")
```

**2. Select a requirement file** from the list that appears.

**3. The pipeline runs automatically:**

```
Finding dependencies...      → results/dependencies/
Generating test cases...     → results/test_cases/
Evaluating SFV metrics...    → results/metrics/
Comparing with expert...     → results/metrics/ (if ground truth exists)
```

**4. Post-generation menu** — optionally run any of:

```
1 -> Back and forth          (iterative LLM refinement)
2 -> Compare with expert     (alignment with human ground truth)
3 -> Coverage analysis       (cross-model stats)
4 -> Evaluate metrics        (re-run Gate 2 SFV)
q -> Quit
```

### HPC Run (IIIT-H Ada Cluster)

```bash
# 1. SSH into the login node
ssh your_username@ada.iiit.ac.in

# 2. Allocate an interactive GPU node
sinteractive -c 10 -A research -g 1

# 3. SSH into the allocated node (check which node was assigned, e.g. gnode025)
ssh gnode025

# 4. Navigate to the pipeline directory and activate the environment
cd ~/pipeline
source venv/bin/activate

# 5. Start Ollama in the background
export LD_LIBRARY_PATH=~/.local/ollama/lib:$LD_LIBRARY_PATH
~/.local/bin/ollama serve > ~/ollama_serve.log 2>&1 &

# 6. Verify Ollama is running
curl -s http://localhost:11434

# 7. Run the pipeline
cd ~/pipeline/pipeline_automated/experiment
python3 -m scripts.cli

# 8. Clean up when done
pkill ollama
deactivate
exit
```

---

## Output Files

After a full run for a requirement file called `REQ_0037.txt`, you will find:

```
results/
├── dependencies/
│   ├── qwen2_5_3b_REQ_0037.json
│   ├── gemma3_4b_REQ_0037.json
│   └── openai_gpt-oss-120b_REQ_0037.json
│
├── test_cases/
│   ├── phase1_basic/
│   │   ├── qwen2_5_3b_REQ_0037/
│   │   │   ├── REQ_0037.txt          ← the generated test suite
│   │   │   └── REQ_0037_meta.json    ← prompt sent + raw response
│   │   ├── gemma3_4b_REQ_0037/
│   │   └── openai_gpt-oss-120b_REQ_0037/
│   └── phase2_metrics_aware/
│       └── ... (same structure)
│
└── metrics/
    ├── phase1_basic/
    │   └── qwen2_5_3b_REQ_0037/
    │       └── REQ_0037_sfv.json     ← Gate 2 SFV score
    ├── phase2_metrics_aware/
    │   └── ...
    └── REQ_0037_sfv_summary.json     ← all models + phases, side by side
```

---

## Key Configuration (`config.py`)

| Setting | Default | Description |
|---|---|---|
| `SFV_THRESHOLD` | 0.60 | Minimum score to pass Gate 2 |
| `FSA_THRESHOLD` | 0.50 | Minimum score to pass Gate 3 |
| `RSS_THRESHOLD` | 0.60 | Minimum score to pass Gate 1 (legacy) |

FSA weights and SFV thresholds vary by representation group (1–6) and
system type (`standard`, `safety_critical`, `data_pipeline`, etc.).
All of these are editable in `config.py` without touching any other file.