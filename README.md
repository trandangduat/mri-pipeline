# MRI Pipeline GUI Demo

Modern `customtkinter` demo for a 9-stage MRI processing pipeline. This prototype only simulates execution; it does not call real tools such as FreeSurfer, SynthSeg, SynthStrip, HD-BET, or ANTs yet.

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
python mri_pipeline_gui.py
```

## Current Features

- Light medical-blue UI built with `customtkinter`.
- Input selection for `.mgz`, `.nii`, `.nii.gz`, `.dcm`, and `.dicom` files.
- Read-only path fields controlled by Browse/Select Folder buttons.
- BIDS Subject ID validation, for example `sub-001`.
- CPU/GPU and thread-count configuration.
- Tool selection for each of the 9 MRI processing stages.
- Step status indicators for Ready, Pending, Running, Success, and Failed states.
- Background-thread simulation so the GUI remains responsive.
- Demo output generation for `subcortical_volume.tsv`, `cortical_volume.tsv`, and `cortical_thickness.tsv`.

## Future Packaging Direction

For a GUI-only prototype, PyInstaller can create a standalone executable:

```bash
pip install pyinstaller
pyinstaller --onefile --windowed mri_pipeline_gui.py
```

For the real MRI pipeline, Docker or Singularity/Apptainer is recommended so large tools such as FreeSurfer, SynthSeg, SynthStrip, HD-BET, and ANTs can be shipped consistently.
