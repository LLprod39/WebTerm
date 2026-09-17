/** Pulls hosts: values from Ansible YAML for operator hints (not inventory resolution). */
export function extractAnsibleHostsHints(sourceYaml: string, limit = 6): string[] {
  const hints: string[] = [];
  const seen = new Set<string>();
  const pattern = /^\s*-?\s*hosts:\s*(.+?)\s*$/gm;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(sourceYaml)) && hints.length < limit) {
    const raw = match[1].replace(/["']/g, "").replace(/#.*$/, "").trim();
    if (!raw || seen.has(raw)) continue;
    seen.add(raw);
    hints.push(raw);
  }
  return hints;
}
