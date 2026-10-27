import React, {useState, useMemo} from 'react';
import {SlidersHorizontal, ChevronDown, RotateCcw, X} from 'lucide-react';
import {BADGE, inputCls} from './ui';
import type {AppMetadata} from '../types/backend';
import type {PipelineFormValues} from '../api/runConfig';
import {selectedToolsFromForm} from '../api/runConfig';

interface ExportItemDef {
  id: string;
  stage: string;
  label: string;
  default_name: string;
}

const FALLBACK_EXPORT_ITEMS: Record<string, ExportItemDef> = {
  'reorientation.primary': {
    id: 'reorientation.primary',
    stage: 'reorientation',
    label: 'Reoriented MRI',
    default_name: '01_reoriented',
  },
  'brain_extraction.primary': {
    id: 'brain_extraction.primary',
    stage: 'brain_extraction',
    label: 'Brain MRI',
    default_name: '02_brain',
  },
  'brain_extraction.mask': {
    id: 'brain_extraction.mask',
    stage: 'brain_extraction',
    label: 'Brain Mask',
    default_name: '02_brain_mask',
  },
  'segmentation.primary': {
    id: 'segmentation.primary',
    stage: 'segmentation',
    label: 'Segmentation',
    default_name: '03_segmentation',
  },
  'template_registration.primary': {
    id: 'template_registration.primary',
    stage: 'template_registration',
    label: 'Registered MRI',
    default_name: '04_registered',
  },
  'template_registration.deformation': {
    id: 'template_registration.deformation',
    stage: 'template_registration',
    label: 'Deformation Field',
    default_name: '04_deformation_field',
  },
  'bias_correction.primary': {
    id: 'bias_correction.primary',
    stage: 'bias_correction',
    label: 'Standardized MRI',
    default_name: '05_standardized',
  },
  'white_matter_segmentation.primary': {
    id: 'white_matter_segmentation.primary',
    stage: 'white_matter_segmentation',
    label: 'White Matter Mask',
    default_name: '06_white_matter_mask',
  },
};

interface ExportNamingSectionProps {
  metadata?: AppMetadata | null | undefined;
  formValues: PipelineFormValues;
  setFormField: (name: string, value: unknown) => void;
  setFormFields: (patch: Record<string, unknown>) => void;
}

export function ExportNamingSection({
  metadata,
  formValues,
  setFormField,
  setFormFields,
}: ExportNamingSectionProps) {
  const [isOpen, setIsOpen] = useState(false);
  const exportEnabled = formValues.exportEnabled ?? false;

  const customNames = useMemo(
    () => (formValues.exportCustomNames as Record<string, string>) || {},
    [formValues.exportCustomNames],
  );

  const pipelineMode = formValues.pipelineMode || 'Custom';
  const isCustom = pipelineMode === 'Custom';

  // Compute active tools for stages
  const effectiveTools = useMemo(() => {
    if (!isCustom && metadata?.presets?.[pipelineMode]?.tools) {
      return metadata.presets[pipelineMode].tools;
    }
    return selectedToolsFromForm(formValues);
  }, [isCustom, pipelineMode, metadata, formValues]);

  // Available export items from backend metadata or fallback
  const allExportItems: ExportItemDef[] = useMemo(() => {
    const rawItems = metadata?.export_items || FALLBACK_EXPORT_ITEMS;
    return Object.values(rawItems);
  }, [metadata]);

  // Filter items matching active stages
  const activeItems = useMemo(() => {
    return allExportItems.filter((item) => {
      const tool = effectiveTools[item.stage];
      return Boolean(tool && String(tool).trim());
    });
  }, [allExportItems, effectiveTools]);

  const customNamesCount = useMemo(() => {
    return Object.entries(customNames).filter(([key, val]) => {
      const matchesActive = activeItems.some((it) => it.id === key);
      return matchesActive && Boolean(val && val.trim());
    }).length;
  }, [customNames, activeItems]);

  const handleNameChange = (itemId: string, newName: string) => {
    const updated = {...customNames};
    const clean = newName.trim();
    if (!clean) {
      delete updated[itemId];
    } else {
      updated[itemId] = clean;
    }
    setFormField('exportCustomNames', updated);
  };

  const handleResetDefaults = (e: React.MouseEvent) => {
    e.stopPropagation();
    setFormFields({exportCustomNames: {}});
  };

  return (
    <div className="rounded-lg border border-cursor-hairline bg-cursor-surface/30 transition-colors">
      <label className="flex items-center justify-between gap-3 px-3 py-3 cursor-pointer">
        <span className="min-w-0">
          <span className="block text-xs font-medium text-cursor-ink">Export output images</span>
          <span className="mt-0.5 block text-2xs text-cursor-muted">
            Save additional image files in {formValues.exportFolder || 'exports'}/.
          </span>
        </span>
        <input
          type="checkbox"
          role="switch"
          checked={exportEnabled}
          onChange={(e) => {
            setFormField('exportEnabled', e.target.checked);
            if (e.target.checked) setIsOpen(true);
          }}
          aria-label="Export output images"
          className="peer sr-only"
        />
        <span
          aria-hidden="true"
          className="relative inline-flex h-5 w-9 shrink-0 rounded-full bg-cursor-muted/40 transition-colors peer-checked:bg-cursor-primary peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-cursor-primary after:absolute after:left-0.5 after:top-0.5 after:h-4 after:w-4 after:rounded-full after:bg-white after:shadow-sm after:transition-transform peer-checked:after:translate-x-4"
        />
      </label>
      {exportEnabled && (
        <>
          {/* Compact Collapsible Header Bar */}
          <button
            type="button"
            onClick={() => setIsOpen((prev) => !prev)}
            className="flex w-full items-center justify-between px-3 py-2 text-left text-cursor-ink transition-colors hover:bg-cursor-canvas-soft/50 border-t border-cursor-hairline"
            aria-expanded={isOpen}
          >
            <div className="flex items-center gap-2 min-w-0">
              <SlidersHorizontal className="h-3.5 w-3.5 text-cursor-primary flex-shrink-0" />
              <span className="text-xs font-medium text-cursor-ink">
                Output filenames
              </span>
              {customNamesCount > 0 ? (
                <span className={`${BADGE.base} ${BADGE.primary} ml-1`}>{customNamesCount} Renamed</span>
              ) : (
                <span className={`${BADGE.base} ${BADGE.neutral} ml-1`}>Default</span>
              )}
            </div>

            <div className="flex items-center gap-2">
              {customNamesCount > 0 && (
                <span
                  role="button"
                  tabIndex={0}
                  onClick={handleResetDefaults}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.stopPropagation();
                      handleResetDefaults(e as unknown as React.MouseEvent);
                    }
                  }}
                  className="inline-flex items-center gap-1 text-2xs text-cursor-muted hover:text-cursor-primary px-1.5 py-0.5 rounded cursor-pointer transition-colors"
                  title="Reset all names to default"
                >
                  <RotateCcw className="h-2.5 w-2.5" />
                  Reset
                </span>
              )}
              <ChevronDown
                className={`h-3.5 w-3.5 text-cursor-muted transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`}
              />
            </div>
          </button>

          {/* Expanded Compact Naming Table */}
          {isOpen && (
            <fieldset className="m-0 min-w-0 border-0 border-t border-cursor-hairline px-3 py-2.5 space-y-1.5">
              <p className="text-2xs text-cursor-muted">
                Blank names use the default filenames.
              </p>
              {activeItems.length === 0 ? (
                <p className="text-2xs text-cursor-muted py-1 italic">
                  {isCustom
                    ? 'Select tools in Pipeline Steps above to enable and rename output images.'
                    : 'No exportable output images for this preset.'}
                </p>
              ) : (
                <div className="space-y-1.5">
                  {activeItems.map((item) => {
                    const currentCustom = customNames[item.id] || '';

                    return (
                      <div
                        key={item.id}
                        className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 sm:gap-3 py-1 border-b border-cursor-hairline-soft/60 last:border-0"
                      >
                        {/* Left: Label & Default Name */}
                        <div className="flex items-center gap-1.5 min-w-0 sm:w-1/2">
                          <span className="text-xs text-cursor-ink font-medium truncate" title={item.label}>
                            {item.label}
                          </span>
                          <span className="text-[9.5px] font-mono text-cursor-muted/80 bg-cursor-surface-strong/40 border border-cursor-hairline-soft/80 px-1 py-0.5 rounded shrink-0 leading-none select-none">
                            {item.default_name}
                          </span>
                        </div>

                        {/* Right: Custom Name Input & Suffix */}
                        <div className="flex items-center gap-1.5 sm:w-1/2 justify-end">
                          <div className="relative flex-1 max-w-[240px] flex items-center">
                            <input
                              type="text"
                              value={currentCustom}
                              placeholder={item.default_name}
                              onChange={(e) => handleNameChange(item.id, e.target.value)}
                              className={`${inputCls} h-6 text-xs font-mono px-2 pr-5 ${
                                currentCustom ? 'border-cursor-primary/70 bg-cursor-primary/5 text-cursor-primary font-medium' : ''
                              }`}
                              title={`Custom filename for ${item.label}`}
                            />
                            {currentCustom ? (
                              <button
                                type="button"
                                onClick={() => handleNameChange(item.id, '')}
                                className="absolute right-1 text-cursor-muted hover:text-cursor-ink p-0.5 cursor-pointer"
                                title="Reset to default name"
                              >
                                <X className="h-2.5 w-2.5" />
                              </button>
                            ) : null}
                          </div>
                          <span className="text-2xs font-mono text-cursor-muted shrink-0 select-none">
                            {(formValues.exportCustomFormats?.[item.id] || formValues.exportDefaultFormat || '.nii.gz') === 'same'
                              ? '(original format)'
                              : (formValues.exportCustomFormats?.[item.id] || formValues.exportDefaultFormat || '.nii.gz')}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </fieldset>
          )}
        </>
      )}
    </div>
  );
}
