from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
from insightface.app import FaceAnalysis
from sklearn.cluster import DBSCAN
from tqdm import tqdm


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
DEFAULT_DBSCAN_EPS = 0.35
DEFAULT_DBSCAN_MIN_SAMPLES = 2


@dataclass
class FaceRecord:
    face_id: str
    bbox_xyxy: list[float]
    det_score: float
    embedding: list[float]
    cluster_id: int | None = None
    name: str | None = None
    review_status: str = "needs_review"


@dataclass
class ImageRecord:
    image_path: str
    width: int
    height: int
    faces: list[FaceRecord]
    keywords: list[str]


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def iter_images(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTS:
            yield path


def cosine_normalize(v: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(v)
    return v if norm == 0 else v / norm


def build_face_app(ctx_id: int = 0, det_size: tuple[int, int] = (640, 640)) -> FaceAnalysis:
    app = FaceAnalysis(name="buffalo_l")
    app.prepare(ctx_id=ctx_id, det_size=det_size)
    return app


def detect_faces_and_embeddings(app: FaceAnalysis, image_path: Path) -> ImageRecord | None:
    img = cv2.imread(str(image_path))
    if img is None:
        print(f"Warning: failed to read {image_path}")
        return None

    height, width = img.shape[:2]
    faces = app.get(img)

    face_records: list[FaceRecord] = []
    for idx, face in enumerate(faces):
        bbox = [float(x) for x in face.bbox.tolist()]
        det_score = float(getattr(face, "det_score", 0.0))
        embedding = cosine_normalize(np.asarray(face.embedding, dtype=np.float32))

        face_records.append(
            FaceRecord(
                face_id=f"{image_path.stem}_f{idx}",
                bbox_xyxy=bbox,
                det_score=det_score,
                embedding=embedding.tolist(),
            )
        )

    return ImageRecord(
        image_path=str(image_path),
        width=width,
        height=height,
        faces=face_records,
        keywords=[],
    )


def cluster_faces(records: list[ImageRecord], eps: float, min_samples: int) -> None:
    all_faces: list[FaceRecord] = []
    embeddings: list[np.ndarray] = []

    for record in records:
        for face in record.faces:
            all_faces.append(face)
            embeddings.append(np.asarray(face.embedding, dtype=np.float32))

    if not all_faces:
        return

    X = np.vstack(embeddings)

    clustering = DBSCAN(
        eps=eps,
        min_samples=min_samples,
        metric="cosine",
        n_jobs=-1,
    )
    labels = clustering.fit_predict(X)

    for face, label in zip(all_faces, labels):
        face.cluster_id = int(label)


def write_manifests(records: list[ImageRecord], out_dir: Path) -> None:
    ensure_dir(out_dir)
    for record in records:
        out_path = out_dir / f"{Path(record.image_path).stem}.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(asdict(record), f, indent=2)


def print_summary(records: list[ImageRecord]) -> None:
    total_images = len(records)
    total_faces = sum(len(r.faces) for r in records)

    cluster_counts: dict[int, int] = {}
    for record in records:
        for face in record.faces:
            cid = face.cluster_id if face.cluster_id is not None else -999
            cluster_counts[cid] = cluster_counts.get(cid, 0) + 1

    print(f"Images processed: {total_images}")
    print(f"Faces detected: {total_faces}")
    print("Clusters:")
    for cid, count in sorted(cluster_counts.items(), key=lambda kv: kv[0]):
        print(f"  {cid}: {count}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detect faces with InsightFace, cluster with DBSCAN, write JSON manifests per image.",
        epilog="Example: python extractFaces.py -i photos/raw -o artifacts/manifests --eps 0.35",
    )
    parser.add_argument("-i", "--input", type=Path, default=Path("photos/raw"), metavar="DIR", help="Image root directory (default: photos/raw)")
    parser.add_argument("-o", "--output", type=Path, default=Path("artifacts/manifests"), metavar="DIR", help="Manifest output directory (default: artifacts/manifests)")
    parser.add_argument("--eps", type=float, default=DEFAULT_DBSCAN_EPS, help=f"DBSCAN eps (default: {DEFAULT_DBSCAN_EPS})")
    parser.add_argument("--min-samples", type=int, default=DEFAULT_DBSCAN_MIN_SAMPLES, help=f"DBSCAN min_samples (default: {DEFAULT_DBSCAN_MIN_SAMPLES})")
    parser.add_argument("--ctx-id", type=int, default=0, help="GPU context id for InsightFace (default: 0; use -1 for CPU)")
    parser.add_argument("--det-size", type=int, nargs=2, default=[640, 640], metavar=("W", "H"), help="Detection size (default: 640 640)")
    args = parser.parse_args()

    image_root = args.input
    manifest_dir = args.output
    ctx_id = args.ctx_id
    det_size = tuple(args.det_size)
    eps = args.eps
    min_samples = args.min_samples

    ensure_dir(manifest_dir)

    image_paths = sorted(iter_images(image_root))
    print(f"Found {len(image_paths)} images")

    app = build_face_app(ctx_id=ctx_id, det_size=det_size)

    records: list[ImageRecord] = []
    for image_path in tqdm(image_paths, desc="Detecting faces"):
        record = detect_faces_and_embeddings(app, image_path)
        if record is not None:
            records.append(record)

    cluster_faces(records, eps=eps, min_samples=min_samples)
    write_manifests(records, manifest_dir)
    print_summary(records)
    print(f"Manifests written to: {manifest_dir}")


if __name__ == "__main__":
    main()