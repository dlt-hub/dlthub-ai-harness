"""Check destination connectivity and dataset existence under a workspace profile.

Exits 0 and prints whether the dataset exists, or exits 1 and prints the traceback.
"""

import argparse
import shutil
import sys
import tempfile
import traceback
import uuid


def main() -> int:
    parser = argparse.ArgumentParser(description="Check destination connectivity and dataset existence.")
    parser.add_argument("profile", help="Workspace profile to activate (e.g. prod, dev)")
    parser.add_argument("destination", help="Destination name, type, or reference (e.g. postgres, warehouse)")
    parser.add_argument("dataset_name", nargs="?", default=None, help="Dataset to check (random if omitted)")
    args = parser.parse_args()

    dataset_name = args.dataset_name or f"_check_{uuid.uuid4().hex[:8]}"

    tmp_dir = tempfile.mkdtemp(prefix="dlt_check_")
    try:
        import dlt

        dlt.current.workspace().switch_profile(args.profile)

        pipeline = dlt.pipeline(
            pipeline_name="_check",
            destination=args.destination,
            dataset_name=dataset_name,
            pipelines_dir=tmp_dir,
        )
        with pipeline.destination_client() as client:
            exists = client.is_storage_initialized()

        status = "exists" if exists else "does not exist"
        print(f"Connection OK. Dataset '{dataset_name}': {status}")
        return 0
    except Exception:
        traceback.print_exc()
        return 1
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
