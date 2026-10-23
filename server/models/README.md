# Detection models

The server loads every model it finds in this folder at startup. Model files are **not in git**
(the weights are ~120 MB), so copy them here by hand.

## Required files

| File | What it is |
|---|---|
| `pest_model.pt` | RF-DETR **Nano** checkpoint fine-tuned on the pest dataset (trained at 640 px). |
| `_annotations.coco.json` | COCO annotations from the same Roboflow export. Only its `categories` list is used, to turn class IDs into pest names. |

The model's name in the API is the file name without its extension (`pest_model`).
A `.pt` model is the default when several are present.

## Other supported formats

- `*.onnx`: loaded with onnxruntime (`rfdtr` in the file name selects the RF-DETR ONNX parser).
- `*.tflite`: needs `tflite_runtime`, which is not installed by default.

## Where to get the files

The Pi project's `.env` holds Google Drive download links (`MODEL_DOWNLOAD_URL`,
`ANNOTATIONS_DOWNLOAD_URL`) for its own model assets. Keep a backup of the server's
`pest_model.pt` and annotations somewhere outside this repository.
