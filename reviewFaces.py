from __future__ import annotations

import argparse
import json
from pathlib import Path

# FiftyOne imported lazily in main() so -h works without loading heavy deps

FACE_FIELD = "faces"
EMBEDDING_FIELD = "face_embeddings"
CLUSTER_FIELD = "face_cluster_ids"


def load_manifests(manifest_dir: Path) -> list[dict]:
    records: list[dict] = []
    for path in sorted(manifest_dir.glob("*.json")):
        with path.open("r", encoding="utf-8") as f:
            records.append(json.load(f))
    return records


def build_dataset(dataset_name: str, records: list[dict], fo, overwrite: bool = True):
    if overwrite and dataset_name in fo.list_datasets():
        fo.delete_dataset(dataset_name)

    dataset = fo.Dataset(dataset_name)

    samples: list[fo.Sample] = []
    for record in records:
        sample = fo.Sample(filepath=record["image_path"])
        sample["width"] = record["width"]
        sample["height"] = record["height"]
        sample["keywords"] = record.get("keywords", [])

        detections = []
        sample_embeddings = []
        sample_cluster_ids = []

        for face in record.get("faces", []):
            x1, y1, x2, y2 = face["bbox_xyxy"]
            width = max(x2 - x1, 1.0)
            height = max(y2 - y1, 1.0)

            rel_box = [
                x1 / record["width"],
                y1 / record["height"],
                width / record["width"],
                height / record["height"],
            ]

            detections.append(
                fo.Detection(
                    label=face["name"] or f'cluster_{face.get("cluster_id", -1)}',
                    bounding_box=rel_box,
                    confidence=face["det_score"],
                    face_id=face["face_id"],
                    cluster_id=face.get("cluster_id"),
                    review_status=face.get("review_status", "needs_review"),
                    person_name=face.get("name"),
                )
            )

            sample_embeddings.append(face["embedding"])
            sample_cluster_ids.append(face.get("cluster_id"))

        sample[FACE_FIELD] = fo.Detections(detections=detections)
        sample[EMBEDDING_FIELD] = sample_embeddings
        sample[CLUSTER_FIELD] = sample_cluster_ids
        samples.append(sample)

    dataset.add_samples(samples)
    return dataset


def add_similarity_index(dataset, fob) -> None:
    vectors = []
    sample_ids = []

    for sample in dataset.iter_samples(progress=True):
        embs = getattr(sample, EMBEDDING_FIELD, None) or []
        if embs:
            vectors.append(embs[0])
            sample_ids.append(sample.id)

    if not vectors:
        print("No embeddings found; skipping similarity index")
        return

    view = dataset.select(sample_ids)
    fob.compute_similarity(
        view,
        embeddings=vectors,
        brain_key="image_similarity",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load face manifests into FiftyOne and launch the review app.",
        epilog="Example: python reviewFaces.py -m artifacts/manifests -d family_faces_v1",
    )
    parser.add_argument("-m", "--manifests", type=Path, default=Path("artifacts/manifests"), metavar="DIR", help="Manifest directory (default: artifacts/manifests)")
    parser.add_argument("-d", "--dataset", default="family_faces_v1", metavar="NAME", help="FiftyOne dataset name (default: family_faces_v1)")
    args = parser.parse_args()

    import fiftyone as fo
    import fiftyone.brain as fob

    manifest_dir = args.manifests
    dataset_name = args.dataset

    records = load_manifests(manifest_dir)
    print(f"Loaded {len(records)} manifest files")

    dataset = build_dataset(dataset_name, records, fo, overwrite=True)
    add_similarity_index(dataset, fob)

    print(f"Dataset ready: {dataset.name}")
    session = fo.launch_app(dataset)
    print("FiftyOne URL:", session.url)
    session.wait()


if __name__ == "__main__":
    main()