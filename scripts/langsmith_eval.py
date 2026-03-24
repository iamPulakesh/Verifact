import sys
import os
import argparse
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langsmith import Client
from langsmith.evaluation import evaluate

from app.agent.runner import run_fact_check
from app.models.verdict import VerdictLabel

def create_dataset(client: Client, dataset_name: str, csv_path: str, num_samples: int = 15):
    """
    Creates or retrieves a dataset in LangSmith from the CSV file.
    """
    if client.has_dataset(dataset_name=dataset_name):
        print(f"Dataset '{dataset_name}' already exists. Using existing examples for comparison.")
        return client.read_dataset(dataset_name=dataset_name)
    
    print(f"Creating dataset '{dataset_name}' with {num_samples} samples from {csv_path}...")
    dataset = client.create_dataset(
        dataset_name=dataset_name,
        description="Fact-check dataset for evaluate Verifact agent."
    )
    
    try:
        df = pd.read_csv(csv_path)
    except UnicodeDecodeError:
        df = pd.read_csv(csv_path, encoding='latin1')
    except Exception as e:
        print(f"Error reading CSV: {e}")
        sys.exit(1)

    df['verdict_str'] = df['verdict'].astype(str).str.lower().str.strip()
    valid_verdicts = {"true": "Real", "false": "Fake", "misleading": "Misleading"}
    
    df = df[df['verdict_str'].isin(valid_verdicts.keys())].dropna(subset=['claim'])
    df = df.head(num_samples)
    
    inputs = []
    outputs = []
    for _, row in df.iterrows():
        inputs.append({"claim": row['claim']})
        outputs.append({"expected_verdict": valid_verdicts[row['verdict_str']]})
        
    client.create_examples(
        inputs=inputs,
        outputs=outputs,
        dataset_id=dataset.id
    )
    print("Dataset created successfully!")
    return dataset

def predict_fact_check(inputs: dict) -> dict:
    """Target function that wraps the main agent for LangSmith."""
    claim = inputs["claim"]
    try:
        # Run the agent
        verdict_obj = run_fact_check(claim, verbose=False)
        return {
            "verdict": verdict_obj.verdict.value,
            "confidence": verdict_obj.confidence_score,
            "reasoning": verdict_obj.reasoning_summary,
            "sources": verdict_obj.sources_consulted
        }
    except Exception as e:
        return {
            "verdict": VerdictLabel.UNVERIFIED.value,
            "confidence": 0.0,
            "reasoning": f"Error: {e}",
            "sources": []
        }

def exact_match_evaluator(run, example) -> dict:
    """Checks if the predicted verdict exactly matches the expected ground truth."""
    # Handle cases where agent failed to produce output
    if not run.outputs:
        return {"key": "verdict_accuracy", "score": 0, "comment": "No output from agent"}
        
    predicted = str(run.outputs.get("verdict", "")).strip().lower()
    expected = str(example.outputs.get("expected_verdict", "")).strip().lower()
    
    is_correct = predicted == expected
    return {
        "key": "verdict_accuracy",
        "score": 1.0 if is_correct else 0.0,
        "comment": f"Predicted: {predicted.capitalize()} | Expected: {expected.capitalize()}"
    }

def confidence_gap_evaluator(run, example) -> dict:
    """Checks if confidence aligns with correctness (calibration)."""
    if not run.outputs:
        return {"key": "confidence_calibration", "score": 0}
        
    predicted = str(run.outputs.get("verdict", "")).strip().lower()
    expected = str(example.outputs.get("expected_verdict", "")).strip().lower()
    confidence = float(run.outputs.get("confidence", 0.0))
    
    is_correct = predicted == expected
    
    # high confidence if correct, low confidence if incorrect.
    score = confidence if is_correct else (1.0 - confidence)
    
    return {
        "key": "confidence_calibration",
        "score": score,
        "comment": f"Confidence: {confidence:.2f}, Correct: {is_correct}"
    }

def main():
    parser = argparse.ArgumentParser("LangSmith Evaluation Script")
    parser.add_argument("--dataset-name", type=str, default="Verifact-model-evaluation", help="Name of the LangSmith dataset")
    parser.add_argument("--csv-path", type=str, default="data/raw/test_data.csv", help="Path to raw CSV dataset")
    parser.add_argument("--samples", type=int, default=15, help="Number of samples to evaluate")
    parser.add_argument("--experiment-prefix", type=str, default="verifact_model_evaluation", help="Prefix for run group")
    args = parser.parse_args()

    if not os.getenv("LANGCHAIN_API_KEY"):
        print("\n[ERROR] LANGCHAIN_API_KEY is not set.")
        sys.exit(1)
        
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_PROJECT"] = args.experiment_prefix

    client = Client()
    
    dataset_name = args.dataset_name
    csv_path = Path(__file__).resolve().parents[1] / args.csv_path

    #  Setup Dataset
    create_dataset(client, dataset_name, str(csv_path), args.samples)

    print(f"\nStarting evaluation on dataset '{dataset_name}'...")
    
    #  Run Evaluation
    experiment_results = evaluate(
        predict_fact_check,
        data=dataset_name,
        evaluators=[
            exact_match_evaluator,
            confidence_gap_evaluator
        ],
        experiment_prefix=args.experiment_prefix,
        metadata={"model": os.getenv("LLM_MODEL", "unknown")},
    )

if __name__ == "__main__":
    main()
