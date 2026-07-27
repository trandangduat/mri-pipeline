# FreeSurfer `recon-all` Surface Tool Research

Research date: 2026-07-24

Question: In FreeSurfer `recon-all`, are there commands/tools that run surface reconstruction, registration, or parcellation steps separately, analogous to using `mri_synthseg` standalone for subcortical segmentation?

## Short Answer

Yes, but with an important qualification. `recon-all` exposes both clustered and step-wise directives for running only parts of the stream, and its surface stream is implemented by separate FreeSurfer command-line binaries such as `mri_tessellate`, `mris_smooth`, `mris_inflate`, `mris_sphere`, `mris_fix_topology`, `mris_register`, `mris_ca_label`, and `mris_anatomical_stats`. However, these are not a single turnkey surface equivalent of `mri_synthseg --i input --o output`; they generally depend on a populated FreeSurfer subject directory and upstream intermediate files, so `recon-all -<step>` or clustered directives are usually the safer interface for running them separately.

## Sources Inspected

| Source | Notes |
|---|---|
| FreeSurfer wiki `recon-all` raw page | Official documentation for directives and step descriptions: `https://surfer.nmr.mgh.harvard.edu/fswiki/recon-all?action=raw`. Line numbers cited from the raw text fetched on 2026-07-24. |
| FreeSurfer 7.4.1 `scripts/recon-all` | Version-pinned source: `https://github.com/freesurfer/freesurfer/blob/fs-7.4.1/scripts/recon-all`. |
| Local run logs | `/mnt/c/Users/ADMIN/Desktop/MRI/frsf_output_9patients/frsf_output/OAS1_0006_MR1/scripts/recon-all.cmd` and `recon-all-status.log`. |

## Findings

`recon-all` is explicitly documented as able to run "all, or any part of" the cortical reconstruction process, not only the complete pipeline. The same page explains that directives can be clustered or step-wise, that step-wise directives implement single reconstruction steps, and that directives can be included or excluded with `-step` or `-nostep` forms. It also states that `-hemi lh|rh` can restrict processing to one hemisphere and can be used to run surface-related steps in parallel. Sources: FreeSurfer wiki raw `recon-all?action=raw`, lines 6, 161-207.

The official wiki lists surface-relevant step-wise directives including `-tessellate`, `-smooth1`, `-inflate1`, `-qsphere`, `-fix`, `-finalsurfs`, `-smooth2`, `-inflate2`, `-cortribbon`, `-sphere`, `-surfreg`, `-contrasurfreg`, `-avgcurv`, `-cortparc`, `-parcstats`, `-cortparc2`, `-parcstats2`, and `-aparc2aseg`. Source: FreeSurfer wiki raw `recon-all?action=raw`, lines 224-241.

The workflow can also be split by broader clustered directives. The wiki describes `-autorecon2` as subcortical segmentation through final surfaces and `-autorecon3` as spherical morph plus automatic cortical parcellation. It also documents editing-oriented restarts such as `-autorecon2-wm`, `-autorecon2-cp`, and `-autorecon2-pial`. Sources: FreeSurfer wiki raw `recon-all?action=raw`, lines 30-42 and 176-204.

The FreeSurfer 7.4.1 script confirms that these step-wise flags are real command-line switches, not only documentation. It parses `-tessellate`, `-smooth1`, `-inflate1`, `-qsphere`, `-fix`, `-whitesurfs`, `-smooth2`, `-inflate2`, `-sphere`, `-surfreg`, `-avgcurv`, `-cortparc`, `-pial`, `-finalsurfs`, `-cortribbon`, and related `-no...` switches into internal booleans. Source: FreeSurfer 7.4.1 `scripts/recon-all`, lines 6563-6819: `https://github.com/freesurfer/freesurfer/blob/fs-7.4.1/scripts/recon-all#L6563-L6819`.

When `-all`/`-autorecon-all` is selected, the 7.4.1 script sets those surface booleans along with the volume steps, including tessellation, smoothing, inflation, topology fixing, spherical mapping, surface registration, average curvature mapping, cortical parcellations, white/pial surfaces, ribbon mask, and parcellation stats. Source: FreeSurfer 7.4.1 `scripts/recon-all`, lines 6970-7000: `https://github.com/freesurfer/freesurfer/blob/fs-7.4.1/scripts/recon-all#L6970-L7000`.

## Tool Mapping

| `recon-all` step | Underlying command/tool in the docs or source | Evidence |
|---|---|---|
| `-tessellate` | `mri_tessellate`, preceded by `mri_pretess` in the script | Wiki says tessellation runs `mri_tessellate`; script builds `mri_pretess` and `mri_tessellate` commands. Sources: wiki raw lines 427-428; script lines 3303-3338: `https://github.com/freesurfer/freesurfer/blob/fs-7.4.1/scripts/recon-all#L3303-L3338`. |
| `-smooth1`, `-smooth2` | `mris_smooth` | Wiki says smoothing calls `mris_smooth`; script builds `mris_smooth` commands for both smoothing passes. Sources: wiki raw lines 430-431; script lines 3370-3385 and 3771-3785: `https://github.com/freesurfer/freesurfer/blob/fs-7.4.1/scripts/recon-all#L3370-L3385`, `https://github.com/freesurfer/freesurfer/blob/fs-7.4.1/scripts/recon-all#L3771-L3785`. |
| `-inflate1`, `-inflate2` | `mris_inflate` | Wiki says inflation calls `mris_inflate`; script builds `mris_inflate` commands for both passes. Sources: wiki raw lines 433-434; script lines 3403-3418 and 3803-3817: `https://github.com/freesurfer/freesurfer/blob/fs-7.4.1/scripts/recon-all#L3403-L3418`, `https://github.com/freesurfer/freesurfer/blob/fs-7.4.1/scripts/recon-all#L3803-L3817`. |
| `-qsphere` | `mris_sphere -q` | Wiki says QSphere calls `mris_sphere`; script builds `mris_sphere -q -p 6 -a 128`. Sources: wiki raw lines 436-437; script lines 3437-3451: `https://github.com/freesurfer/freesurfer/blob/fs-7.4.1/scripts/recon-all#L3437-L3451`. |
| `-fix` | `mris_fix_topology`, with possible fallback/new path using `mris_topo_fixer` | Wiki says the topology fixer calls `mris_fix_topology`; script builds `mris_fix_topology` and includes a `mris_topo_fixer` path. Sources: wiki raw lines 439-440; script lines 3470-3491 and 3545-3567: `https://github.com/freesurfer/freesurfer/blob/fs-7.4.1/scripts/recon-all#L3470-L3491`, `https://github.com/freesurfer/freesurfer/blob/fs-7.4.1/scripts/recon-all#L3545-L3567`. |
| `-finalsurfs` / white/pial surfaces | Wiki: `mris_make_surfaces`; FreeSurfer 7.4.1 source: `-finalsurfs` maps to `DoWhiteSurfs` and `DoPialSurfs`, implemented with `mris_place_surface` | The wiki still describes final surfaces as `mris_make_surfaces`, while the 7.4.1 script uses `mris_place_surface` for white and pial placement. Sources: wiki raw lines 442-443; script lines 6799-6808, 4214-4229, and 4278-4298: `https://github.com/freesurfer/freesurfer/blob/fs-7.4.1/scripts/recon-all#L6799-L6808`, `https://github.com/freesurfer/freesurfer/blob/fs-7.4.1/scripts/recon-all#L4214-L4229`, `https://github.com/freesurfer/freesurfer/blob/fs-7.4.1/scripts/recon-all#L4278-L4298`. |
| `-sphere` | `mris_sphere` | Wiki says spherical inflation calls `mris_sphere`; script builds `mris_sphere` from inflated surface to sphere. Sources: wiki raw lines 448-449; script lines 3931-3950: `https://github.com/freesurfer/freesurfer/blob/fs-7.4.1/scripts/recon-all#L3931-L3950`. |
| `-surfreg` | `mris_register` | Wiki says surface registration calls `mris_register`; script builds `mris_register -curv` using the hemisphere-specific atlas. Sources: wiki raw lines 451-452; script lines 3969-3992: `https://github.com/freesurfer/freesurfer/blob/fs-7.4.1/scripts/recon-all#L3969-L3992`. |
| `-avgcurv` | `mrisp_paint` | Wiki says average curvature calls `mrisp_paint`; script builds `mrisp_paint -a 5`. Sources: wiki raw lines 457-458; script lines 4093-4109: `https://github.com/freesurfer/freesurfer/blob/fs-7.4.1/scripts/recon-all#L4093-L4109`. |
| `-cortparc`, `-cortparc2`, `-cortparc3` | `mris_ca_label` | Wiki says cortical parcellation calls `mris_ca_label`; script builds `mris_ca_label` for Desikan-Killiany and related atlases. Sources: wiki raw lines 460-461; script lines 4128-4152: `https://github.com/freesurfer/freesurfer/blob/fs-7.4.1/scripts/recon-all#L4128-L4152`. |
| `-parcstats`, `-parcstats2`, `-parcstats3` | `mris_anatomical_stats` | Wiki says parcellation statistics run `mris_anatomical_stats`; script builds `mris_anatomical_stats` commands. Sources: wiki raw lines 463-464; script lines 4961-4981 and 5004-5020: `https://github.com/freesurfer/freesurfer/blob/fs-7.4.1/scripts/recon-all#L4961-L4981`, `https://github.com/freesurfer/freesurfer/blob/fs-7.4.1/scripts/recon-all#L5004-L5020`. |

## Local Log Evidence

The local `OAS1_0006_MR1` run shows the standalone nature of the subcortical SynthSeg call: `mri_synthseg --i ... --o ... --vol ... --keepgeom --addctab --cpu`, producing `mri/synthseg.rca.mgz` and `stats/synthseg.vol.csv`. Source: `/mnt/c/Users/ADMIN/Desktop/MRI/frsf_output_9patients/frsf_output/OAS1_0006_MR1/scripts/recon-all.log`, lines 311-324.

The same local run also records separate command-line binaries for surface steps: `mri_tessellate`, `mris_smooth`, `mris_inflate`, `mris_sphere`, `mris_fix_topology`, `mris_register`, `mrisp_paint`, and `mris_ca_label`. Source: `/mnt/c/Users/ADMIN/Desktop/MRI/frsf_output_9patients/frsf_output/OAS1_0006_MR1/scripts/recon-all.cmd`, lines 130-193 and 248-337.

The local run shows FreeSurfer 8.1.0 using `mris_place_surface` for white and pial surfaces, matching the 7.4.1 source pattern rather than the older wiki wording that names `mris_make_surfaces`. Source: `/mnt/c/Users/ADMIN/Desktop/MRI/frsf_output_9patients/frsf_output/OAS1_0006_MR1/scripts/recon-all.cmd`, lines 340-354.

The local status file confirms these surface operations are distinct status milestones, including tessellation, smoothing, inflation, QSphere, topology fix, sphere, surface registration, average curvature, cortical parcellation, ribbon mask, and parcellation stats. Source: `/mnt/c/Users/ADMIN/Desktop/MRI/frsf_output_9patients/frsf_output/OAS1_0006_MR1/scripts/recon-all-status.log`, lines 20-29, 36-45, and 60-78.

## Practical Interpretation

For a completed or partially completed FreeSurfer subject, the supported way to run surface portions separately is usually via `recon-all` directives, for example:

```bash
recon-all -s SUBJECT -autorecon3
recon-all -s SUBJECT -hemi lh -sphere -surfreg -cortparc -parcstats
recon-all -s SUBJECT -hemi lh -tessellate -smooth1 -inflate1 -qsphere -fix
```

Directly invoking the underlying tools is possible because they are normal FreeSurfer command-line programs, but the source and logs show they require specific upstream inputs and naming conventions such as `mri/filled.mgz`, `mri/norm.mgz`, `surf/?h.orig.nofix`, `surf/?h.inflated`, `surf/?h.sphere.reg`, atlas `.tif` files, atlas `.gcs` files, cortex labels, and `aseg.presurf.mgz`. This makes them less analogous to `mri_synthseg` as a standalone one-command segmentation tool and more like individually callable stages inside a stateful subject reconstruction.

## Conclusion

FreeSurfer does provide separate commands/tools for surface reconstruction, spherical registration, cortical parcellation, and parcellation statistics. The closest analog to "run this piece separately" is usually `recon-all` with step-wise directives and optional `-hemi`, not a single independent surface-reconstruction replacement for the whole surface stream. The underlying binaries can be called directly, but they are tightly coupled to the `recon-all` subject directory and intermediate outputs.
