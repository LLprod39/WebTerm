export type PipelineEditorLang = "en" | "ru";

export type LocalizedText = Record<PipelineEditorLang, string>;
export type LocalizedList = Record<PipelineEditorLang, string[]>;

export type NodeTypeMeta = {
  label: LocalizedText;
  paletteDescription: LocalizedText;
};

export type NodeGuidanceMeta = {
  category: LocalizedText;
  summary: LocalizedText;
  checklist: LocalizedList;
};
