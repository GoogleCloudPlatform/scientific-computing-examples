#!/usr/bin/env python3
"""Unit tests for google_skills_router.py."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from google_skills_router import (
    CURATED_GOOGLE_SKILLS,
    CURATED_SCIENCE_SKILLS,
    check_science_prerequisites,
    load_google_skills_index,
    recommend_skills,
    validate_fetch_command,
    validate_index_payload,
)


class TestGoogleSkillsRouterStandalone(unittest.TestCase):
    def test_validate_fetch_command(self):
        ok, errs = validate_fetch_command(
            "curl -sSL https://raw.githubusercontent.com/google/skills/main/index.json -o skills-index.json"
        )
        self.assertTrue(ok)
        self.assertEqual(errs, [])

        for bad in (
            "curl -k https://raw.githubusercontent.com/google/skills/main/index.json",
            "curl -sSLk https://raw.githubusercontent.com/google/skills/main/index.json",
            "curl --insecure https://raw.githubusercontent.com/google/skills/main/index.json",
            "curl -sSL http://raw.githubusercontent.com/google/skills/main/index.json",
            "",
        ):
            ok_bad, _ = validate_fetch_command(bad)
            self.assertFalse(ok_bad, f"Expected bad command to fail: {bad}")

    def test_curated_catalogs_completeness_and_entrypoints(self):
        # All 40 DeepMind science skills must be present
        self.assertEqual(len(CURATED_SCIENCE_SKILLS), 40)
        by_name = {s["name"]: s for s in CURATED_GOOGLE_SKILLS}
        self.assertEqual(
            by_name["finding-google-skills"]["entrypoint"],
            "skills/developers/finding-google-skills/SKILL.md",
        )
        self.assertEqual(
            by_name["retrieving-developer-knowledge"]["entrypoint"],
            "skills/developers/retrieving-developer-knowledge/SKILL.md",
        )

    def test_validate_index_payload(self):
        ok, _ = validate_index_payload(
            {
                "skills": [
                    {
                        "name": "gcloud",
                        "description": "gcloud CLI skill",
                        "entrypoint": "skills/cloud/gcloud/SKILL.md",
                    }
                ]
            }
        )
        self.assertTrue(ok)
        self.assertFalse(validate_index_payload({"skills": []})[0])
        self.assertFalse(validate_index_payload({})[0])

    def test_safe_credentials_never_leaks_secret_values(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = os.path.join(tmpdir, ".env")
            secret = "SECRET_VALUE_DO_NOT_EXPOSE_12345"
            with open(env_file, "w", encoding="utf-8") as f:
                f.write(f"ALPHAGENOME_API_KEY={secret}\n")

            res = check_science_prerequisites(
                required_env_keys=["ALPHAGENOME_API_KEY", "OPENALEX_API_KEY"],
                env_file=env_file,
                workspace_dir=tmpdir,
                skill_name="chembl_database",
                write_license_receipt=True,
            )
            self.assertTrue(res["credential_presence"]["ALPHAGENOME_API_KEY"])
            self.assertFalse(res["credential_presence"]["OPENALEX_API_KEY"])
            self.assertTrue(res["license_recorded"])
            self.assertNotIn(secret, json.dumps(res))

    def test_recommend_skills_routing_and_full_url_entrypoints(self):
        plan = recommend_skills(
            query="gcsfuse local ssd cache filestore", domain="storage", top_k=5
        )
        matched_names = [m["name"] for m in plan["all_matches"]]
        self.assertIn("google-cloud-storage-fuse", matched_names)

        # Ensure live index.json style full URL entrypoints do not double-prefix
        with tempfile.TemporaryDirectory() as tmpdir:
            idx_file = os.path.join(tmpdir, "index.json")
            full_url = "https://raw.githubusercontent.com/google/skills/refs/heads/main/skills/cloud/gke-batch-hpc/SKILL.md"
            with open(idx_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "skills": [
                            {
                                "name": "gke-batch-hpc",
                                "description": "Run batch and HPC workloads on GKE",
                                "entrypoint": full_url,
                            }
                        ]
                    },
                    f,
                )
            live_plan = recommend_skills(
                query="gke batch hpc", domain="gke", index_file=idx_file, top_k=5
            )
            gke_match = [
                m for m in live_plan["google_skills_matches"] if m["name"] == "gke-batch-hpc"
            ][0]
            self.assertEqual(gke_match["raw_url"], full_url)
            self.assertEqual(gke_match["raw_url"].count("https://"), 1)


if __name__ == "__main__":
    unittest.main()

