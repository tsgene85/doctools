from __future__ import annotations

import argparse
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_manifests(manifest_dir: Path) -> list[dict]:
    records: list[dict] = []
    for path in sorted(manifest_dir.glob("*.json")):
        with path.open("r", encoding="utf-8") as f:
            records.append(json.load(f))
    return records


def make_voc_xml(record: dict, images_out: Path) -> ET.Element:
    root = ET.Element("annotation")

    ET.SubElement(root, "folder").text = "images"
    ET.SubElement(root, "filename").text = Path(record["image_path"]).name
    ET.SubElement(root, "path").text = str((images_out / Path(record["image_path"]).name).resolve())

    source = ET.SubElement(root, "source")
    ET.SubElement(source, "database").text = "Unknown"

    size = ET.SubElement(root, "size")
    ET.SubElement(size, "width").text = str(record["width"])
    ET.SubElement(size, "height").text = str(record["height"])
    ET.SubElement(size, "depth").text = "3"

    ET.SubElement(root, "segmented").text = "0"

    for face in record.get("faces", []):
        obj = ET.SubElement(root, "object")
        ET.SubElement(obj, "name").text = face.get("name") or "face"
        ET.SubElement(obj, "pose").text = "Unspecified"
        ET.SubElement(obj, "truncated").text = "0"
        ET.SubElement(obj, "difficult").text = "0"

        bndbox = ET.SubElement(obj, "bndbox")
        x1, y1, x2, y2 = [int(round(v)) for v in face["bbox_xyxy"]]
        ET.SubElement(bndbox, "xmin").text = str(x1)
        ET.SubElement(bndbox, "ymin").text = str(y1)
        ET.SubElement(bndbox, "xmax").text = str(x2)
        ET.SubElement(bndbox, "ymax").text = str(y2)

    return root


def write_xml(root: ET.Element, out_path: Path) -> None:
    tree = ET.ElementTree(root)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export face manifests to CVAT-friendly Pascal VOC (images + XML annotations).",
        epilog="Example: python export_cvat.py -m artifacts/manifests -o artifacts/cvat_export",
    )
    parser.add_argument("-m", "--manifests", type=Path, default=Path("artifacts/manifests"), metavar="DIR", help="Manifest directory (default: artifacts/manifests)")
    parser.add_argument("-o", "--output", type=Path, default=Path("artifacts/cvat_export"), metavar="DIR", help="Export directory (default: artifacts/cvat_export)")
    args = parser.parse_args()

    manifest_dir = args.manifests
    export_dir = args.output
    images_out = export_dir / "images"
    annotations_out = export_dir / "annotations"

    ensure_dir(images_out)
    ensure_dir(annotations_out)

    records = load_manifests(manifest_dir)
    print(f"Loaded {len(records)} manifest files")

    for record in records:
        src_image = Path(record["image_path"])
        dst_image = images_out / src_image.name
        if not dst_image.exists():
            shutil.copy2(src_image, dst_image)

        xml_root = make_voc_xml(record, images_out)
        xml_path = annotations_out / f"{src_image.stem}.xml"
        write_xml(xml_root, xml_path)

    print(f"CVAT export written to: {export_dir}")
    print("Import images + Pascal VOC XML into CVAT")


if __name__ == "__main__":
    main()