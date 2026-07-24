export type CreateAgentSavedPayload = {
  id: number;
  mode: "mini" | "full" | "multi";
  action: "create" | "update";
  runAfterSave: boolean;
};
