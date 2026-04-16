/**
 * src/api/studio.ts — Pipeline, MCP, Skills, Triggers API.
 *
 * Migration target for functions from src/lib/api.ts related to:
 *   - Pipelines (fetchPipelines, createPipeline, runPipeline, etc.)
 *   - Pipeline runs (fetchRuns, fetchRunDetail, stopRun, approveNode)
 *   - MCP Hub (fetchMcpServers, createMcpServer, testMcp, fetchMcpTools)
 *   - Skills (fetchSkills, createSkill, fetchSkillTemplates, etc.)
 *   - Triggers (fetchTriggers, createTrigger, deleteTrigger)
 *   - Agent configs (fetchAgentConfigs, createAgentConfig, etc.)
 *   - Notifications (fetchNotificationSettings, saveNotificationSettings)
 *
 * Status: re-exported from src/api/index.ts (pending migration)
 */
