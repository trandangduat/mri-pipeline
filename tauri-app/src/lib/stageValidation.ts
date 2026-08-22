import type {AppMetadata} from '../types/backend';
import {selectedToolsFromForm, type PipelineFormValues} from '../api/runConfig';

export interface StageViolation {
  stageId: string;
  toolKey: string;
  reason: string;
  missing: string[];
}

export const EMPTY_STAGE_VIOLATIONS: StageViolation[] = [];

interface ToolContract {
  requires: string[];
  produces: string[];
}

function nonEmptyTools(selectedTools: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [stage, tool] of Object.entries(selectedTools)) {
    if (tool && tool.trim()) out[stage] = tool.trim();
  }
  return out;
}

function matchesNamedPreset(metadata: AppMetadata, tools: Record<string, string>): boolean {
  if (!Object.keys(tools).length) return false;
  const toolEntries = Object.entries(tools).sort();
  return Object.values(metadata.presets || {}).some((preset) => {
    const presetEntries = Object.entries(nonEmptyTools(preset.tools)).sort();
    return (
      presetEntries.length === toolEntries.length &&
      presetEntries.every(([stage, tool], i) => {
        const other = toolEntries[i];
        return other !== undefined && stage === other[0] && tool === other[1];
      })
    );
  });
}

export function effectiveStageOrder(metadata: AppMetadata, selectedTemplateTool: string): string[] {
  return selectedTemplateTool === 'fs7_recon_style_template_registration'
    ? metadata.fs7_recon_style_stage_order
    : metadata.stage_order;
}

export function validateSelectedTools(
  metadata: AppMetadata,
  selectedTools: Record<string, string>,
): StageViolation[] {
  const tools = nonEmptyTools(selectedTools);
  if (!Object.keys(tools).length) {
    return [{stageId: '*', toolKey: '', reason: 'No pipeline steps selected.', missing: []}];
  }
  if (matchesNamedPreset(metadata, tools)) return EMPTY_STAGE_VIOLATIONS;

  const contracts = metadata.tool_contracts || {};
  const available = new Set<string>(['raw_input']);
  const violations: StageViolation[] = [];
  for (const stage of effectiveStageOrder(metadata, tools.template_registration || '')) {
    const toolKey = tools[stage];
    if (!toolKey) continue;
    const contract: ToolContract | undefined = contracts[toolKey];
    if (!contract) continue;
    const missing = contract.requires.filter((token) => !available.has(token));
    if (missing.length) {
      violations.push({stageId: stage, toolKey, reason: buildReason(metadata, toolKey, missing), missing});
      continue;
    }
    for (const token of contract.produces) available.add(token);
  }
  return violations;
}

const TOKEN_LABELS: Record<string, string> = {
  raw_input: 'the input image',
  orig_mgz: 'conformed orig.mgz (enable a Reorientation step)',
  nifti_volume: 'a NIfTI volume from an earlier step',
  cat12_seg: 'CAT12 segmentation outputs',
  seg_fastsurfer: 'FastSurfer segmentation outputs',
  seg_synthseg_rca: 'SynthSeg RCA outputs',
  seg_nifti: 'a standalone NIfTI segmentation',
  seg_fs7: 'FreeSurfer 7 atlas segmentation (aseg.presurf.mgz)',
  be_fs7_brainmask: 'the FreeSurfer 7 brain mask (brainmask.mgz)',
  be_synthstrip_mgz: 'the SynthStrip skull-stripped volume',
  be_nifti: 'a skull-stripped NIfTI brain',
  talairach_xfm: 'the Talairach transform from Template Registration',
  nu_talairach: 'nu.mgz intensity-corrected against the Talairach transform',
  bias_norm_fs: 'bias-corrected FreeSurfer volumes',
  wm_filled: 'white-matter segmentation (wm.mgz / filled.mgz)',
  surfaces_preaparc_fs7: 'FreeSurfer 7 pre-parcellation surfaces',
  surfaces_final: 'final surfaces (lh/rh.white, lh/rh.pial)',
  sphere_reg: 'registered spheres (lh/rh.sphere.reg)',
  dkt_annots: 'DKTatlas mapped annotations',
  stats_tsvs: 'volume stats tables',
  stats_aparc: 'parcellation stats files',
};

function buildReason(metadata: AppMetadata, toolKey: string, missing: string[]): string {
  const displayName = metadata.tools?.[toolKey]?.display_name || toolKey.replace(/_/g, ' ');
  const labels = missing.map((token) => TOKEN_LABELS[token] || token).join(', ');
  return `${displayName} cannot run: the selection does not produce ${labels}.`;
}

export function validateStageTools(
  metadata: AppMetadata,
  formValues: PipelineFormValues,
): StageViolation[] {
  if (formValues.pipelineMode !== 'Custom') return EMPTY_STAGE_VIOLATIONS;
  return validateSelectedTools(metadata, selectedToolsFromForm(formValues));
}
