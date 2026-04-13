# CVAT Getting Started

**CVAT** (Computer Vision Annotation Tool) is an open-source platform for labeling images, video, and 3D data. Use it to draw boxes, polygons, and other shapes, manage labels, run AI-assisted annotation, and export datasets.

---

## 1. How to start CVAT

You can run CVAT in two ways: **hosted online** (no install) or **self-hosted with Docker** (full control, on-premises).

### Option A: CVAT Online (fastest)

1. Go to **[app.cvat.ai](https://app.cvat.ai)**.
2. Sign up or log in.
3. Start creating projects and tasks in the browser. No Docker or install required.

Best for trying CVAT quickly; storage and plans are described at [cvat.ai/pricing](https://www.cvat.ai/pricing/cvat-online).

### Option B: Self-hosted with Docker

Runs on your machine or server. You need **Docker** and **Docker Compose** (and **Git** to clone the repo).

**Windows (with WSL2):**

1. Install [WSL2](https://docs.microsoft.com/windows/wsl/install-win10) and a Linux distro.
2. Install [Docker Desktop for Windows](https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe) and enable WSL2 integration.
3. Install [Git for Windows](https://git-scm.com/download/win).
4. Open your WSL/Linux terminal and run:

```bash
git clone https://github.com/cvat-ai/cvat
cd cvat
docker compose up -d
```

**Linux (e.g. Ubuntu):**

```bash
# Install Docker and Docker Compose first (see docs.docker.com), then:
git clone https://github.com/cvat-ai/cvat
cd cvat
docker compose up -d
```

**Create an admin user (self-hosted only):**

New users have no rights until an admin assigns them. Create a superuser:

```bash
docker exec -it cvat_server bash -ic 'python3 ~/manage.py createsuperuser'
```

Enter username, email (optional), and password.

**Open CVAT:**

- Local: **[http://localhost:8080](http://localhost:8080)**  
- From another machine: set `CVAT_HOST` to your hostname or IP before `docker compose up -d`, then use `http://<CVAT_HOST>:8080`.

**Recommended browser:** Chrome (officially supported).

---

## 2. First steps in the UI

1. **Log in** with your account (or the superuser you created).
2. **Projects** – Organize work by project (e.g. “face_review”). Each project has a label set (e.g. `face`, `person`).
3. **Tasks** – A task holds one dataset: a list of images or one video. You open a task to annotate.
4. **Jobs** – Large tasks are split into jobs (slices of frames) assigned to annotators.

Typical flow: **Create project → Add task → Upload images/video (and optionally annotations) → Open task → Annotate → Export.**

---

## 3. Creating a project and task

### Create a project

1. Go to **Projects** → **Create new project**.
2. **Name:** e.g. `face_review`.
3. **Labels:** Add at least one label (e.g. `face`). You can add more later. Optionally set attributes (e.g. `occluded`: checkbox).
4. Save.

### Create a task

1. Open the project → **Add new task** (or create a standalone task from **Tasks**).
2. **Name:** e.g. `batch_01`.
3. **Data:**
   - **Upload files:** Add images (e.g. from `artifacts/cvat_export/images/`) or a video file. Supported: JPEG, PNG, BMP, etc.; video via ffmpeg (MP4, AVI, MOV, etc.).
   - **Upload annotations (optional):** If you have pre-made labels (e.g. from `export_cvat.py`), choose format **Pascal VOC 1.1** and upload the XML files from `artifacts/cvat_export/annotations/`.
4. Submit. The task is built; then open it to annotate.

---

## 4. Main features

### Annotation modes

The workspace can run in different modes (often selectable in the toolbar or via shortcuts):

| Mode | Purpose |
|------|--------|
| **Standard** | Full annotation: draw and edit all shape types. |
| **Single shape** | Draw one shape, then exit drawing automatically. |
| **Review** | Only review and validate existing annotations (approve/reject). |
| **Attribute annotation** | Edit object attributes (e.g. labels, flags) without changing geometry. |
| **Tag** | Add frame-level tags (no shapes), e.g. for classification. |

### Shape tools

Used to define object geometry:

| Tool | Use case |
|------|----------|
| **Rectangle** | Bounding boxes (e.g. face detection, object detection). Draw with two opposite corners. |
| **Polygon** | Complex outlines (e.g. segmentation, irregular objects). |
| **Polyline** | Lines and curves (e.g. roads, limbs in pose). |
| **Ellipse** | Ovals and circles. |
| **Skeleton** | Pose/keypoints (e.g. human pose). |
| **Brush** | Free-form pixel masks (e.g. segmentation). |
| **Cuboid** | 3D boxes (3D tasks). |

For face boxes from `export_cvat.py`, you mainly use **Rectangle** to add or correct detections.

### Shapes vs tracks

- **Shape** – One object on one frame (typical for images or per-frame detection).
- **Track** – Same object across many frames (for video); CVAT links the object over time.

When you draw, the UI usually lets you choose “Shape” or “Track”.

### Drawing and editing

- **Draw:** Pick a tool (e.g. Rectangle) and a label, then draw on the canvas. For rectangles: click two opposite corners.
- **Select:** Click a shape to select it. Resize by dragging corners or edges; move by dragging.
- **Change label:** Select object, then pick another label in the sidebar or attributes panel.
- **Delete:** Select and press **Delete** or use the object sidebar.
- **Copy/paste:** Duplicate shapes between frames (useful in video).

### Keyboard shortcuts

- **Save:** `Ctrl+S` (save often).
- **Next/previous frame:** `F` / `D` (or as shown in the player).
- **Shortcuts help:** Open **Settings** (gear) → **Shortcuts** to see and customize shortcuts. Many UI elements show their shortcut on hover.

Shortcuts are scoped (e.g. global vs annotation workspace); conflicts are shown in settings.

### AI and automation

CVAT can run models to pre-annotate or assist:

- **Detectors:** e.g. YOLO, Faster R-CNN, face detection (built-in or custom).
- **Segment Anything (SAM):** Interactive segmentation.
- **Trackers:** Propagate a box across video frames.

Access via the **AI tools** or **Models** in the task UI (availability depends on deployment; CVAT Online has integrations like Hugging Face and Roboflow).

### Review and QA

- In **Review** mode you only approve or reject annotations.
- Issues can be raised on frames; annotators fix and re-submit.
- Use **Menu → Export dataset** when done to download annotations (Pascal VOC, COCO, CVAT XML, etc.).

---

## 5. Exporting annotations

When a task is done:

1. Open the task (or project).
2. **Menu** (three dots) → **Export dataset**.
3. Choose format (e.g. **Pascal VOC 1.1**, **COCO 1.0**, **CVAT for images 1.1**).
4. Download the archive.

Use this to get corrected labels back into your pipeline (e.g. convert to your own format or re-import into FiftyOne).

---

## 6. Using CVAT with doctools export

The script **export_cvat.py** writes images and Pascal VOC XML so CVAT can load them:

```bash
python export_cvat.py -m artifacts/manifests -o artifacts/cvat_export
```

You get:

- **`artifacts/cvat_export/images/`** – image files  
- **`artifacts/cvat_export/annotations/`** – one XML per image (face boxes and labels)

In CVAT:

1. Create a **project** with a label (e.g. `face`) matching your XML.
2. **Add new task** → upload all files from **`cvat_export/images`**.
3. **Upload annotations** → format **Pascal VOC 1.1** → select the **`annotations`** folder or the XML files.
4. Open the task: review or edit face boxes, then **Export dataset** if you need the updated annotations.

Details are also in **COMMAND_LINE.md** under “Using CVAT with the export”.

---

## 7. Useful links

| Resource | Description |
|----------|-------------|
| [CVAT docs](https://docs.cvat.ai/docs/) | Full documentation. |
| [Installation (self-hosted)](https://docs.cvat.ai/docs/administration/community/basics/installation/) | Detailed Docker and OS-specific install. |
| [Dataset formats](https://docs.cvat.ai/docs/dataset_management/formats/) | Import/export formats (Pascal VOC, COCO, etc.). |
| [Shortcuts](https://docs.cvat.ai/docs/getting_started/shortcuts/) | Keyboard shortcut reference and customization. |
| [CVAT GitHub](https://github.com/cvat-ai/cvat) | Source and issues. |

---

## Quick reference

| Goal | Action |
|------|--------|
| Run CVAT without install | Use [app.cvat.ai](https://app.cvat.ai). |
| Run CVAT locally | `git clone` → `cd cvat` → `docker compose up -d` → open http://localhost:8080. |
| Create admin (self-hosted) | `docker exec -it cvat_server bash -ic 'python3 ~/manage.py createsuperuser'`. |
| Annotate | Projects → Create project (with labels) → Add task → Upload images (+ optional annotations) → Open task → Draw/edit → Save. |
| Import doctools export | Upload `cvat_export/images` as task data; upload `cvat_export/annotations` as Pascal VOC 1.1. |
| Export labels | Task menu → Export dataset → choose format. |
