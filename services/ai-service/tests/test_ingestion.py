from pathlib import Path

from app.ingestion.main import run_pipeline


def test_run_pipeline():
    pdf = Path(__file__).parent / "test-data" / "sample.pdf"

    # Run the full pipeline
    num_chunks = run_pipeline(
        file_path=str(pdf),
        workspace_id="test-workspace",
        allowed_role_ids=["viewer", "admin"],
    )

    # Ensure that some chunks were stored
    assert num_chunks > 0 