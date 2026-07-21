from __future__ import annotations

TOOL_DEFS: dict[str, dict] = {
    "mri_convert_fs8": {
        "display_name": "MRI Convert FreeSurfer8",
        "image": "mkdayyyy/mri-fs8-all:latest",
        "stage": "reorientation",
        "needs_license": True,
        "command_builder": lambda ctx: f"mri_convert {'-no-dcm2niix -dicomread2 --sdcmlist ' + ctx.dicom_list_path + ' ' if ctx.dicom_list_path else ''}{ctx.input_path} /work/01_reoriented.nii.gz",
        "output_files": ["01_reoriented.nii.gz"],
    },
    "mri_convert_fs7": {
        "display_name": "MRI Convert FreeSurfer7",
        "image": "mkdayyyy/mri-fs7-all:latest",
        "stage": "reorientation",
        "needs_license": True,
        "command_builder": lambda ctx: f"mri_convert {'-no-dcm2niix -dicomread2 --sdcmlist ' + ctx.dicom_list_path + ' ' if ctx.dicom_list_path else ''}{ctx.input_path} /work/01_reoriented.nii.gz",
        "output_files": ["01_reoriented.nii.gz"],
    },
    "nibabel": {
        "display_name": "NiBabel",
        "image": "duattran05/mri-nibabel-utils:latest",
        "dockerfile": "docker/nibabel-utils",
        "stage": "reorientation",
        "needs_license": False,
        "output_files": ["01_nibabel_reoriented.nii.gz"],
    },
    "synthstrip_fs8": {
        "display_name": "SynthStrip FreeSurfer8",
        "image": "mkdayyyy/mri-fs8-all:latest",
        "stage": "brain_extraction",
        "needs_license": True,
        "command_builder": lambda ctx: (
            f"mri_synthstrip -i {ctx.input_path} "
            f"-o /work/02_synthstrip_brain.nii.gz "
            f"-m /work/02_synthstrip_brain_mask.nii.gz "
            f"{'-g' if ctx.device != 'cpu' else ''}"
        ),
        "output_files": ["02_synthstrip_brain.nii.gz", "02_synthstrip_brain_mask.nii.gz"],
    },
    "synthstrip_fs7": {
        "display_name": "SynthStrip FreeSurfer7",
        "image": "mkdayyyy/mri-fs7-all:latest",
        "stage": "brain_extraction",
        "needs_license": True,
        "command_builder": lambda ctx: (
            f"mri_synthstrip -i {ctx.input_path} "
            f"-o /work/02_synthstrip_brain.nii.gz "
            f"-m /work/02_synthstrip_brain_mask.nii.gz "
            f"{'-g' if ctx.device != 'cpu' else ''}"
        ),
        "output_files": ["02_synthstrip_brain.nii.gz", "02_synthstrip_brain_mask.nii.gz"],
    },
    "hdbet": {
        "display_name": "HD-BET",
        "image": "duattran05/mri-hdbet:latest",
        "dockerfile": "docker/hdbet",
        "stage": "brain_extraction",
        "needs_license": False,
        "entrypoint": "",
        "shell": "sh",
        "command_builder": lambda ctx: (
            f"hd-bet -i {ctx.input_path} "
            f"-o /work/02_hdbet_brain.nii.gz "
            f"-device {'cpu' if ctx.device == 'cpu' else '0'} "
            f"--save_bet_mask "
            f"{'--disable_tta' if ctx.device == 'cpu' else ''}"
        ),
        "output_files": ["02_hdbet_brain.nii.gz", "02_hdbet_brain_mask.nii.gz"],
        "extra_mounts": {"hdbet_weights": "/root/.cache/torch/hub/checkpoints"},
    },
    "synthseg_freesurfer_fs8": {
        "display_name": "SynthSeg FreeSurfer8",
        "image": "mkdayyyy/mri-fs8-all:latest",
        "stage": "segmentation",
        "needs_license": True,
        "command_builder": lambda ctx: (
            f"mri_synthseg --i {ctx.input_path} --o /work/03_freesurfer_synthseg_segmentation.nii.gz "
            f"--vol /work/03_freesurfer_synthseg_volumes.csv --parc --threads {ctx.threads} --crop 160 "
            f"{'--cpu' if ctx.device == 'cpu' else ''} "
            f"&& python3 /app/normalize_volumes.py /work/03_freesurfer_synthseg_volumes.csv "
            f"/output/stats/subcortical_volume.tsv /output/stats/cortical_volume.tsv {ctx.subject_id} FreeSurferSynthSeg"
        ),
        "output_files": ["03_freesurfer_synthseg_segmentation.nii.gz"],
    },
    "synthseg_freesurfer_fs7": {
        "display_name": "SynthSeg FreeSurfer7",
        "image": "mkdayyyy/mri-fs7-all:latest",
        "stage": "segmentation",
        "needs_license": True,
        "command_builder": lambda ctx: (
            f"mri_synthseg --i {ctx.input_path} --o /work/03_freesurfer_synthseg_segmentation.nii.gz "
            f"--vol /work/03_freesurfer_synthseg_volumes.csv --parc --threads {ctx.threads} --crop 160 "
            f"{'--cpu' if ctx.device == 'cpu' else ''} "
            f"&& python3 /app/normalize_volumes.py /work/03_freesurfer_synthseg_volumes.csv "
            f"/output/stats/subcortical_volume.tsv /output/stats/cortical_volume.tsv {ctx.subject_id} FreeSurferSynthSeg"
        ),
        "output_files": ["03_freesurfer_synthseg_segmentation.nii.gz"],
    },
    "synthseg_standalone": {
        "display_name": "SynthSeg Standalone",
        "image": "duattran05/mri-synthseg-standalone:latest",
        "dockerfile": "docker/synthseg-standalone",
        "stage": "segmentation",
        "needs_license": False,
        "output_files": ["03_synthseg_standalone_segmentation.nii.gz"],
    },
    "fastsurfervinn": {
        "display_name": "FastSurferVINN",
        "image": "duattran05/mri-fastsurfervinn:latest",
        "dockerfile": "docker/fastsurfervinn",
        "stage": "segmentation",
        "needs_license": True,
        "output_files": ["03_fastsurfervinn_segmentation.nii.gz", "aparc.DKTatlas+aseg.deep.mgz"],
    },
    "ants_n4": {
        "display_name": "ANTs N4",
        "image": "duattran05/mri-ants:latest",
        "dockerfile": "docker/ants",
        "stage": "bias_correction",
        "needs_license": False,
        "output_files": ["05_standardized.nii.gz"],
    },
    "synthmorph_fs8": {
        "display_name": "SynthMorph FreeSurfer8",
        "image": "mkdayyyy/mri-fs8-all:latest",
        "stage": "template_registration",
        "needs_license": True,
        "command_builder": lambda ctx: (
            f"mri_synthmorph register -m deform -j {ctx.threads} "
            f"-o /work/04_synthmorph_registered.nii.gz {ctx.input_path} {ctx.input_path}"
        ),
        "output_files": [
            "04_warped.nii.gz",
            "04_deformation_field.nii.gz",
            "04_synthmorph_warped.nii.gz",
            "04_synthmorph_deformation_field.nii.gz",
        ],
        "output_globs": [
            "*warped*.nii*",
            "*moved*.nii*",
            "*registered*.nii*",
            "*warped*.mgz",
            "*moved*.mgz",
            "*registered*.mgz",
        ],
    },
    "mri_binarize": {
        "display_name": "MRI Binarize FreeSurfer7",
        "image": "mkdayyyy/mri-fs7-all:latest",
        "stage": "white_matter_segmentation",
        "needs_license": True,
        "command_builder": lambda ctx: f"mri_binarize --i {ctx.input_path} --wm --o /work/06_wm_mask.nii.gz",
        "output_files": ["06_wm_mask.nii.gz"],
    },
    "mri_binarize_fs8": {
        "display_name": "MRI Binarize FreeSurfer8",
        "image": "mkdayyyy/mri-fs8-all:latest",
        "stage": "white_matter_segmentation",
        "needs_license": True,
        "command_builder": lambda ctx: f"mri_binarize --i {ctx.input_path} --wm --o /work/06_wm_mask.nii.gz",
        "output_files": ["06_wm_mask.nii.gz"],
    },
    "recon_all_fs7": {
        "display_name": "Recon-All FreeSurfer7",
        "image": "mkdayyyy/mri-fs7-all:latest",
        "stage": "surface_reconstruction",
        "needs_license": True,
        "command_builder": lambda ctx: (
            "set -e; "
            "export SUBJECTS_DIR=/output/freesurfer; "
            "mkdir -p \"$SUBJECTS_DIR\" /output/stats; "
            "input=/work/mri/01_reoriented.nii.gz; "
            "if [ ! -s \"$input\" ]; then input=/work/mri/05_standardized.nii.gz; fi; "
            f"if [ ! -s \"$input\" ]; then input={ctx.input_path}; fi; "
            f"if [ -d \"$SUBJECTS_DIR/{ctx.subject_id}\" ] && [ ! -s \"$SUBJECTS_DIR/{ctx.subject_id}/surf/lh.thickness\" ]; then rm -rf \"$SUBJECTS_DIR/{ctx.subject_id}\"; fi; "
            f"recon-all -sd \"$SUBJECTS_DIR\" -s {ctx.subject_id} -i \"$input\" -all -parallel -openmp {ctx.threads}; "
            f"cp \"$SUBJECTS_DIR/{ctx.subject_id}/stats/\"*.stats /output/stats/ 2>/dev/null || true"
        ),
        "output_files": [],
        "output_globs": [
            "freesurfer/*/surf/lh.thickness",
            "freesurfer/*/surf/rh.thickness",
            "freesurfer/*/stats/lh.aparc.stats",
            "freesurfer/*/stats/rh.aparc.stats",
        ],
    },
    "recon_all_fs8": {
        "display_name": "Recon-All FreeSurfer8",
        "image": "mkdayyyy/mri-fs8-all:latest",
        "stage": "surface_reconstruction",
        "needs_license": True,
        "command_builder": lambda ctx: (
            "set -e; "
            "export SUBJECTS_DIR=/output/freesurfer; "
            "mkdir -p \"$SUBJECTS_DIR\" /output/stats; "
            "input=/work/mri/01_reoriented.nii.gz; "
            "if [ ! -s \"$input\" ]; then input=/work/mri/05_standardized.nii.gz; fi; "
            f"if [ ! -s \"$input\" ]; then input={ctx.input_path}; fi; "
            f"if [ -d \"$SUBJECTS_DIR/{ctx.subject_id}\" ] && [ ! -s \"$SUBJECTS_DIR/{ctx.subject_id}/surf/lh.thickness\" ]; then rm -rf \"$SUBJECTS_DIR/{ctx.subject_id}\"; fi; "
            f"recon-all -sd \"$SUBJECTS_DIR\" -s {ctx.subject_id} -i \"$input\" -all -parallel -openmp {ctx.threads}; "
            f"cp \"$SUBJECTS_DIR/{ctx.subject_id}/stats/\"*.stats /output/stats/ 2>/dev/null || true"
        ),
        "output_files": [],
        "output_globs": [
            "freesurfer/*/surf/lh.thickness",
            "freesurfer/*/surf/rh.thickness",
            "freesurfer/*/stats/lh.aparc.stats",
            "freesurfer/*/stats/rh.aparc.stats",
        ],
    },
    "surface_stats_fs7": {
        "display_name": "Surface Stats FreeSurfer7",
        "image": "mkdayyyy/mri-fs7-all:latest",
        "stage": "surface_registration",
        "needs_license": True,
        "command_builder": lambda ctx: (
            "set -e; "
            "export SUBJECTS_DIR=/output/freesurfer; "
            "mkdir -p /output/stats; "
            "if [ ! -e \"$SUBJECTS_DIR/fsaverage\" ] && [ -d \"$FREESURFER_HOME/subjects/fsaverage\" ]; then ln -s \"$FREESURFER_HOME/subjects/fsaverage\" \"$SUBJECTS_DIR/fsaverage\"; fi; "
            f"test -s \"$SUBJECTS_DIR/{ctx.subject_id}/surf/lh.thickness\"; "
            f"test -s \"$SUBJECTS_DIR/{ctx.subject_id}/surf/rh.thickness\"; "
            f"cp \"$SUBJECTS_DIR/{ctx.subject_id}/stats/\"*.stats /output/stats/; "
            f"for atlas in YBA_696parcels 200Parcels_Kong2022_17Networks schaefer200_7network; do for hemi in lh rh; do annot=\"$SUBJECTS_DIR/{ctx.subject_id}/label/$hemi.$atlas.annot\"; fsavg=\"$SUBJECTS_DIR/fsaverage/label/$hemi.$atlas.annot\"; if [ ! -s \"$annot\" ] && [ -s \"$fsavg\" ]; then mri_surf2surf --srcsubject fsaverage --trgsubject {ctx.subject_id} --hemi \"$hemi\" --sval-annot \"$fsavg\" --tval \"$annot\" >/tmp/mri_surf2surf.log 2>&1 || true; fi; if [ -s \"$annot\" ]; then mris_anatomical_stats -a \"$annot\" -f \"/output/stats/$hemi.$atlas.stats\" {ctx.subject_id} \"$hemi\" >/tmp/mris_anatomical_stats.log 2>&1 || true; fi; done; done; "
            "test -s /output/stats/lh.aparc.stats; "
            "test -s /output/stats/rh.aparc.stats"
        ),
        "output_files": ["lh.aparc.stats", "rh.aparc.stats"],
    },
    "surface_stats_fs8": {
        "display_name": "Surface Stats FreeSurfer8",
        "image": "mkdayyyy/mri-fs8-all:latest",
        "stage": "surface_registration",
        "needs_license": True,
        "command_builder": lambda ctx: (
            "set -e; "
            "export SUBJECTS_DIR=/output/freesurfer; "
            "mkdir -p /output/stats; "
            "if [ ! -e \"$SUBJECTS_DIR/fsaverage\" ] && [ -d \"$FREESURFER_HOME/subjects/fsaverage\" ]; then ln -s \"$FREESURFER_HOME/subjects/fsaverage\" \"$SUBJECTS_DIR/fsaverage\"; fi; "
            f"test -s \"$SUBJECTS_DIR/{ctx.subject_id}/surf/lh.thickness\"; "
            f"test -s \"$SUBJECTS_DIR/{ctx.subject_id}/surf/rh.thickness\"; "
            f"cp \"$SUBJECTS_DIR/{ctx.subject_id}/stats/\"*.stats /output/stats/; "
            f"for atlas in YBA_696parcels 200Parcels_Kong2022_17Networks schaefer200_7network; do for hemi in lh rh; do annot=\"$SUBJECTS_DIR/{ctx.subject_id}/label/$hemi.$atlas.annot\"; fsavg=\"$SUBJECTS_DIR/fsaverage/label/$hemi.$atlas.annot\"; if [ ! -s \"$annot\" ] && [ -s \"$fsavg\" ]; then mri_surf2surf --srcsubject fsaverage --trgsubject {ctx.subject_id} --hemi \"$hemi\" --sval-annot \"$fsavg\" --tval \"$annot\" >/tmp/mri_surf2surf.log 2>&1 || true; fi; if [ -s \"$annot\" ]; then mris_anatomical_stats -a \"$annot\" -f \"/output/stats/$hemi.$atlas.stats\" {ctx.subject_id} \"$hemi\" >/tmp/mris_anatomical_stats.log 2>&1 || true; fi; done; done; "
            "test -s /output/stats/lh.aparc.stats; "
            "test -s /output/stats/rh.aparc.stats"
        ),
        "output_files": ["lh.aparc.stats", "rh.aparc.stats"],
    },
    "freesurfer_stats_fs7": {
        "display_name": "FreeSurfer Stats FreeSurfer7",
        "image": "mkdayyyy/mri-fs7-all:latest",
        "stage": "stats_extraction",
        "needs_license": True,
        "command_builder": lambda ctx: "test -s /output/stats/subcortical_volume.tsv && test -s /output/stats/cortical_volume.tsv",
        "output_files": [
            "subcortical_volume.tsv",
            "cortical_volume.tsv",
        ],
    },
    "freesurfer_stats_fs8": {
        "display_name": "FreeSurfer Stats FreeSurfer8",
        "image": "mkdayyyy/mri-fs8-all:latest",
        "stage": "stats_extraction",
        "needs_license": True,
        "command_builder": lambda ctx: "test -s /output/stats/subcortical_volume.tsv && test -s /output/stats/cortical_volume.tsv",
        "output_files": [
            "subcortical_volume.tsv",
            "cortical_volume.tsv",
        ],
    },
    "corticalflow": {
        "display_name": "CorticalFlow++",
        "image": "duattran05/mri-corticalflow:latest",
        "dockerfile": "docker/corticalflow",
        "stage": "surface_reconstruction",
        "needs_license": False,
        "entrypoint": "",
        "shell": "bash",
        "command_builder": lambda ctx: (
            f"cd /app && python3 predict.py inputs.data_type=list inputs.path={ctx.input_path} "
            f"inputs.split_name={ctx.subject_id} outputs.output_dir=/work/corticalflow_out "
            f"inputs.device={'cuda:0' if ctx.device != 'cpu' else 'cpu'}"
        ),
        "output_files": [],
        "output_globs": ["corticalflow_out/*/*white*", "corticalflow_out/*/*pial*"],
    },
    "sugar": {
        "display_name": "SUGAR",
        "image": "ninganme/sugar:latest",
        "dockerfile": "docker/sugar",
        "stage": "surface_registration",
        "needs_license": False,
        "entrypoint": "",
        "shell": "bash",
        "command_builder": lambda ctx: (
            "PREDICT=$(find / -name predict.py -path '*/SUGAR/predict.py' | head -n 1); "
            f"python3 $PREDICT --sd /output/freesurfer --out /work/sugar_out --fsd /usr/local/freesurfer "
            f"--sid {ctx.subject_id} --hemi lh --device {'cuda' if ctx.device != 'cpu' else 'cpu'} && "
            f"python3 $PREDICT --sd /output/freesurfer --out /work/sugar_out --fsd /usr/local/freesurfer "
            f"--sid {ctx.subject_id} --hemi rh --device {'cuda' if ctx.device != 'cpu' else 'cpu'}"
        ),
        "output_files": [],
        "output_globs": ["sugar_out/*"],
    },
}

TOOL_DISPLAY_ALIASES = {
    "Mri Convert FS8": "mri_convert_fs8",
    "Mri Convert FS7": "mri_convert_fs7",
    "Mri Convert Fs8": "mri_convert_fs8",
    "Mri Convert Fs7": "mri_convert_fs7",
    "FreeSurfer SynthSeg FS8": "synthseg_freesurfer_fs8",
    "FreeSurfer SynthSeg FS7": "synthseg_freesurfer_fs7",
    "FreeSurfer SynthSeg Fs8": "synthseg_freesurfer_fs8",
    "FreeSurfer SynthSeg Fs7": "synthseg_freesurfer_fs7",
    "Mri Binarize": "mri_binarize",
    "MRI Binarize": "mri_binarize",
    "Mri Binarize FS8": "mri_binarize_fs8",
    "MRI Binarize FS8": "mri_binarize_fs8",
    "FreeSurfer Stats FS7": "freesurfer_stats_fs7",
    "FreeSurfer Stats FS8": "freesurfer_stats_fs8",
    "CorticalFlow": "corticalflow",
    "CorticalFlow++": "corticalflow",
    "Sugar": "sugar",
    "SUGAR": "sugar",
}

DISABLED_DOCKER_IMAGES: set[str] = set()

STAGE_ORDER = [
    "reorientation",
    "brain_extraction",
    "segmentation",
    "template_registration",
    "bias_correction",
    "white_matter_segmentation",
    "surface_reconstruction",
    "surface_registration",
    "stats_extraction",
]

STAGE_LABELS = {
    "reorientation": "Reorientation, resize",
    "brain_extraction": "Brain Extraction",
    "segmentation": "Subcortical Segmentation",
    "template_registration": "Template Registration",
    "bias_correction": "Image standardization",
    "white_matter_segmentation": "WM Segmentation",
    "surface_reconstruction": "Surface Reconstruction",
    "surface_registration": "Surface Registration",
    "stats_extraction": "Statistics & Atlas Mapping",
}

def tool_display_name(tool_key: str) -> str:
    tool = TOOL_DEFS.get(tool_key)
    if not tool:
        return ""
    return str(tool.get("display_name") or tool_key.replace("_", " ").title())

def tool_key_from_display(value: str) -> str:
    if value in TOOL_DEFS:
        return value
    if value in TOOL_DISPLAY_ALIASES:
        return TOOL_DISPLAY_ALIASES[value]
    for tool_key in TOOL_DEFS:
        if tool_display_name(tool_key) == value:
            return tool_key
    return ""

def is_tool_enabled(tool_key: str) -> bool:
    tool = TOOL_DEFS.get(tool_key)
    if not tool:
        return False
    return tool.get("image") not in DISABLED_DOCKER_IMAGES and not tool.get("disabled", False)

def enabled_tools_for_stage(stage: str) -> list[str]:
    return [key for key, tool in TOOL_DEFS.items() if tool["stage"] == stage and is_tool_enabled(key)]

