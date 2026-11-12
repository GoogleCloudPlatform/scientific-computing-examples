#!/usr/bin/env bash
# Blueprint Validator for Google Cloud Cluster Toolkit (ghpc / gcluster)
# Validates YAML cluster blueprint syntax and schema with lint fallback.

set -e

BLUEPRINT_FILE="${1:-deployment.yaml}"

if [ ! -f "$BLUEPRINT_FILE" ]; then
  echo "[-] Error: Blueprint file not found: $BLUEPRINT_FILE" >&2
  exit 1
fi

echo "[*] Validating Cluster Toolkit blueprint: $BLUEPRINT_FILE"

# 1. Primary validation using ghpc or gcluster if it supports 'validate'
VALIDATOR_CMD=""
if command -v gcluster &>/dev/null && gcluster validate --help &>/dev/null; then
  VALIDATOR_CMD="gcluster"
elif command -v ghpc &>/dev/null && ghpc validate --help &>/dev/null; then
  VALIDATOR_CMD="ghpc"
fi

if [ -n "$VALIDATOR_CMD" ]; then
  echo "[+] Found toolkit CLI: $VALIDATOR_CMD"
  echo "[*] Running '$VALIDATOR_CMD validate $BLUEPRINT_FILE'..."
  if "$VALIDATOR_CMD" validate "$BLUEPRINT_FILE"; then
    echo "[✓] Blueprint passed $VALIDATOR_CMD validation!"
    exit 0
  else
    echo "[-] $VALIDATOR_CMD validation failed!" >&2
    exit 1
  fi
fi

# 2. Fallback YAML parsing and structural validation
echo "[i] Toolkit CLI (ghpc / gcluster) not found in PATH. Using YAML lint & schema validator fallback..."

python3 - << 'EOF' "$BLUEPRINT_FILE"
import sys
import yaml

filepath = sys.argv[1]

# 1. Syntax check
try:
    with open(filepath, "r") as f:
        data = yaml.safe_load(f)
except Exception as e:
    print(f"[-] YAML Syntax Error in {filepath}:\n{e}", file=sys.stderr)
    sys.exit(1)

if not isinstance(data, dict):
    print(f"[-] Blueprint error: Top-level structure must be a mapping/dict, got {type(data)}", file=sys.stderr)
    sys.exit(1)

# 2. Blueprint name check
if "blueprint_name" not in data:
    print("[-] Missing required key: 'blueprint_name'", file=sys.stderr)
    sys.exit(1)

print(f"[+] Blueprint Name: {data['blueprint_name']}")

# 3. Deployment groups or spec check
groups = None
if "spec" in data and isinstance(data["spec"], dict):
    spec = data["spec"]
    groups = spec.get("deployment_groups")
    vars_dict = spec.get("vars", {})
elif "deployment_groups" in data:
    groups = data["deployment_groups"]
    vars_dict = data.get("vars", {})
else:
    print("[-] Missing required section: 'deployment_groups' or 'spec.deployment_groups'", file=sys.stderr)
    sys.exit(1)

if not groups or not isinstance(groups, list):
    print("[-] 'deployment_groups' must be a non-empty list", file=sys.stderr)
    sys.exit(1)

module_count = 0
for idx, grp in enumerate(groups):
    if not isinstance(grp, dict) or "modules" not in grp:
        print(f"[-] Deployment group #{idx} missing 'modules' list", file=sys.stderr)
        sys.exit(1)
    for mod in grp.get("modules", []):
        if not isinstance(mod, dict) or "id" not in mod or "source" not in mod:
            print(f"[-] Invalid module in group #{idx}: missing 'id' or 'source'", file=sys.stderr)
            sys.exit(1)
        module_count += 1

print(f"[+] Found {len(groups)} deployment group(s) with {module_count} valid module definitions.")

# 4. Optional yamllint check if available
try:
    import subprocess
    if subprocess.run(["which", "yamllint"], capture_output=True).returncode == 0:
        res = subprocess.run(["yamllint", "-d", "{rules: {line-length: disable}}", filepath], capture_output=True, text=True)
        if res.returncode == 0:
            print("[+] yamllint check passed cleanly.")
        else:
            print(f"[!] yamllint notices:\n{res.stdout}")
except Exception:
    pass

print(f"[✓] Blueprint schema & syntax validation PASSED: {filepath}")
EOF

exit $?
